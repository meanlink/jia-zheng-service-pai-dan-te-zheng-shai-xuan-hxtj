from fastapi import HTTPException
from pymysql.err import IntegrityError

from .db import audit, today, transaction
from .models import ORDER_FIELDS, TECH_FIELDS


def orders():
    with transaction() as cur:
        cur.execute("""SELECT o.*,p.id AS plan_id,p.status AS plan_status
          FROM service_orders o LEFT JOIN dispatch_plans p ON p.order_id=o.id
          ORDER BY (o.status='followed_up'),o.service_date DESC,o.id DESC LIMIT 150""")
        return cur.fetchall()


def create_order(data, actor):
    if data.service_date < today():
        raise HTTPException(422, '预约日期不能早于上海业务日期')
    fields = data.model_dump()
    try:
        with transaction() as cur:
            cur.execute(f'INSERT INTO service_orders ({",".join(fields)}) VALUES ({",".join(["%s"] * len(fields))})',
                        tuple(fields.values()))
            order_id = cur.lastrowid
            audit(cur, actor, 'order_received', data.code, service=data.service, service_date=data.service_date)
            cur.execute(f'SELECT {ORDER_FIELDS} FROM service_orders WHERE id=%s', (order_id,))
            return cur.fetchone()
    except IntegrityError as exc:
        if exc.args[0] == 1062:
            raise HTTPException(409, '受理工单号已存在') from exc
        raise


def technicians():
    with transaction() as cur:
        cur.execute(f'SELECT {TECH_FIELDS} FROM technicians ORDER BY skill,id')
        return cur.fetchall()


def renew_qualification(technician_id, data, actor):
    try:
        with transaction() as cur:
            cur.execute(f'SELECT {TECH_FIELDS} FROM technicians WHERE id=%s FOR UPDATE', (technician_id,))
            technician = cur.fetchone()
            if technician is None:
                raise HTTPException(404, '技师不存在')
            if data.valid_through < today() or data.valid_through <= technician['valid_through']:
                raise HTTPException(422, '续期必须晚于原到期日，且覆盖当前业务日期')
            cur.execute('UPDATE technicians SET certificate=%s,valid_through=%s WHERE id=%s',
                        (data.certificate, data.valid_through, technician_id))
            audit(cur, actor, 'qualification_renewed', technician['code'],
                  subject_kind='technician', previous=technician['certificate'], current=data.certificate,
                  previous_expiry=technician['valid_through'], valid_through=data.valid_through)
            cur.execute(f'SELECT {TECH_FIELDS} FROM technicians WHERE id=%s', (technician_id,))
            return cur.fetchone()
    except IntegrityError as exc:
        if exc.args[0] == 1062:
            raise HTTPException(409, '该证书编号已用于另一位技师') from exc
        raise
