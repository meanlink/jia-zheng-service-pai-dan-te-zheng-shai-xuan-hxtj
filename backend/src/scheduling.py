from fastapi import HTTPException

from .db import audit, today, transaction


def initialize():
    with transaction() as cur:
        cur.execute('''CREATE TABLE IF NOT EXISTS technician_time_off (
            id INT AUTO_INCREMENT PRIMARY KEY,
            technician_id INT NOT NULL,
            off_date DATE NOT NULL,
            slot ENUM('am','pm','evening') NOT NULL,
            reason VARCHAR(500) NOT NULL,
            UNIQUE KEY technician_slot (technician_id,off_date,slot),
            FOREIGN KEY (technician_id) REFERENCES technicians(id)
        ) CHARACTER SET utf8mb4''')
        cur.execute('''CREATE TABLE IF NOT EXISTS customer_visit_contacts (
            id INT AUTO_INCREMENT PRIMARY KEY,
            order_id INT NOT NULL,
            outcome ENUM('confirmed','reschedule','moved') NOT NULL,
            service_date DATE NOT NULL,
            slot ENUM('am','pm','evening') NOT NULL,
            note VARCHAR(500) NOT NULL,
            actor VARCHAR(48) NOT NULL,
            recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            KEY order_contacts (order_id,id),
            FOREIGN KEY (order_id) REFERENCES service_orders(id)
        ) CHARACTER SET utf8mb4''')


def time_offs():
    with transaction() as cur:
        cur.execute('''SELECT b.*,t.name FROM technician_time_off b JOIN technicians t
                       ON t.id=b.technician_id WHERE b.off_date >= %s ORDER BY b.off_date,b.slot,b.id''', (today(),))
        return cur.fetchall()


def require_available(cur, technician, order):
    cur.execute('''SELECT id FROM technician_time_off WHERE technician_id=%s AND off_date=%s AND slot=%s''',
                (technician['id'], order['service_date'], order['slot']))
    if cur.fetchone():
        raise HTTPException(409, '技师该预约时段停工，请另选技师')


def add_time_off(data, actor):
    from .dispatch import get_technician

    if data.off_date < today():
        raise HTTPException(422, '停工日期不能早于业务日')
    with transaction() as cur:
        tech = get_technician(cur, data.technician_id, lock=True)
        require_available(cur, tech, {'service_date': data.off_date, 'slot': data.slot})
        cur.execute('''SELECT o.code FROM dispatch_plans p JOIN service_orders o ON o.id=p.order_id
                       WHERE p.technician_id=%s AND o.status='assigned' AND o.service_date=%s AND o.slot=%s LIMIT 1''',
                    (tech['id'], data.off_date, data.slot))
        if conflict := cur.fetchone():
            raise HTTPException(409, f"该时段有已派工单 {conflict['code']}")
        cur.execute('INSERT INTO technician_time_off(technician_id,off_date,slot,reason) VALUES (%s,%s,%s,%s)',
                    (tech['id'], data.off_date, data.slot, data.note))
        identifier = cur.lastrowid
        audit(cur, actor, 'time_off_added', tech['code'], subject_kind='technician',
              date=data.off_date, slot=data.slot, reason=data.note)
        return {'id': identifier}


def remove_time_off(identifier, actor):
    from .dispatch import get_technician

    with transaction() as cur:
        cur.execute('SELECT technician_id FROM technician_time_off WHERE id=%s', (identifier,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, '停工记录不存在')
        tech = get_technician(cur, row['technician_id'], lock=True)
        cur.execute('DELETE FROM technician_time_off WHERE id=%s AND off_date >= %s', (identifier, today()))
        if cur.rowcount != 1:
            raise HTTPException(409, '记录已撤销或停工已过期')
        audit(cur, actor, 'time_off_removed', tech['code'], subject_kind='technician', time_off_id=identifier)


def contacts():
    with transaction() as cur:
        cur.execute('''SELECT c.*,o.code FROM customer_visit_contacts c JOIN service_orders o ON o.id=c.order_id
                       ORDER BY c.id DESC LIMIT 100''')
        return cur.fetchall()


def latest_contact(cur, order_id):
    cur.execute('SELECT outcome FROM customer_visit_contacts WHERE order_id=%s ORDER BY id DESC LIMIT 1', (order_id,))
    return cur.fetchone()


def require_resolved_contact(cur, order_id):
    contact = latest_contact(cur, order_id)
    if contact and contact['outcome'] == 'reschedule':
        raise HTTPException(409, '客户已要求改期，请完成改期或重新确认原时段')


def record_contact(order_id, data, actor):
    from .dispatch import get_order, invalidate_analysis

    with transaction() as cur:
        order = get_order(cur, order_id, lock=True)
        if order['status'] != 'received':
            raise HTTPException(409, '只可调整待派工单')
        target_date, target_slot = order['service_date'], order['slot']
        if data.outcome == 'moved':
            contact = latest_contact(cur, order_id)
            if not contact or contact['outcome'] != 'reschedule':
                raise HTTPException(409, '请先登记客户改期请求')
            if data.service_date is None or data.slot is None or data.service_date < today():
                raise HTTPException(422, '请选择有效的新日期和时段')
            target_date, target_slot = data.service_date, data.slot
            if (target_date, target_slot) == (order['service_date'], order['slot']):
                raise HTTPException(422, '请选择与原预约不同的时段')
            cur.execute('UPDATE service_orders SET service_date=%s,slot=%s WHERE id=%s',
                        (target_date, target_slot, order_id))
            invalidate_analysis(cur, order_id, '预约已改期，请重新分析')
        elif data.service_date is not None or data.slot is not None:
            raise HTTPException(422, '仅完成改期时可填写新日期和时段')
        elif data.outcome == 'confirmed' and target_date < today():
            raise HTTPException(422, '原预约已过期，请改期')
        cur.execute('''INSERT INTO customer_visit_contacts(order_id,outcome,service_date,slot,note,actor)
                       VALUES (%s,%s,%s,%s,%s,%s)''',
                    (order_id, data.outcome, target_date, target_slot, data.note, actor))
        identifier = cur.lastrowid
        audit(cur, actor, 'visit_contact', order['code'], outcome=data.outcome,
              old_date=order['service_date'], old_slot=order['slot'], new_date=target_date, new_slot=target_slot)
        return {'id': identifier, 'service_date': target_date, 'slot': target_slot}
