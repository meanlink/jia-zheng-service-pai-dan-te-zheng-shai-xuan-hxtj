import json

from fastapi import HTTPException

from .db import audit, transaction

SCOPE_FIELDS = ('area_m2', 'dirt_level', 'obstacles', 'supplies')


def current_scope(order):
    return {**{key: order[key] for key in SCOPE_FIELDS}, 'supplies': bool(order['supplies'])}


def latest(cur, order_id):
    cur.execute('SELECT * FROM order_scope_revisions WHERE order_id=%s ORDER BY revision_no DESC LIMIT 1', (order_id,))
    row = cur.fetchone()
    if row:
        row['previous_scope'] = json.loads(row['previous_scope'])
    return row


def require_received(order):
    if order['status'] != 'received':
        raise HTTPException(409, '只可调整待派工单')


def require_decision(cur, order_id):
    row = latest(cur, order_id)
    if row and row['status'] == 'pending':
        raise HTTPException(409, '客户补测待主管复核，暂不能派单')


def propose(order_id, data, actor):
    from .dispatch import get_order

    with transaction() as cur:
        order = get_order(cur, order_id, lock=True)
        require_received(order)
        prior = latest(cur, order_id)
        if prior and prior['status'] == 'pending':
            raise HTTPException(409, '已有待复核的补测单')
        previous = current_scope(order)
        revised = data.model_dump(include=set(SCOPE_FIELDS))
        if revised == previous:
            raise HTTPException(422, '至少修改一项作业范围')
        number = prior['revision_no'] + 1 if prior else 1
        cur.execute('''INSERT INTO order_scope_revisions(order_id,revision_no,previous_scope,area_m2,dirt_level,
                      obstacles,supplies,reason,submitted_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                    (order_id, number, json.dumps(previous), *[revised[key] for key in SCOPE_FIELDS], data.note, actor))
        audit(cur, actor, 'scope_proposed', order['code'], revision=number, proposed=revised)
        return latest(cur, order_id)


def decide(order_id, revision_id, data, actor):
    from .dispatch import get_order, invalidate_analysis

    with transaction() as cur:
        order = get_order(cur, order_id, lock=True)
        require_received(order)
        revision = latest(cur, order_id)
        if not revision or revision['id'] != revision_id or revision['status'] != 'pending':
            raise HTTPException(409, '这条补测单已处理或不是当前待复核版本')
        if data.decision == 'approved':
            cur.execute('''UPDATE service_orders SET area_m2=%s,dirt_level=%s,obstacles=%s,supplies=%s WHERE id=%s''',
                        (*[revision[key] for key in SCOPE_FIELDS], order_id))
            invalidate_analysis(cur, order_id, '作业范围已更新，请重新分析')
        cur.execute('''UPDATE order_scope_revisions SET status=%s,decision_note=%s,decided_by=%s,
                       decided_at=CURRENT_TIMESTAMP WHERE id=%s''', (data.decision, data.note, actor, revision_id))
        audit(cur, actor, 'scope_decided', order['code'], revision=revision['revision_no'], decision=data.decision)
        return latest(cur, order_id)
