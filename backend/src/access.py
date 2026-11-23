from fastapi import HTTPException

from .db import audit, transaction
from .scope import require_received


def clearance(cur, order_id):
    cur.execute('SELECT * FROM order_access_clearances WHERE order_id=%s', (order_id,))
    return cur.fetchone()


def require_access(cur, order_id):
    row = clearance(cur, order_id)
    if row and row['status'] == 'blocked':
        raise HTTPException(409, '入户条件未落实，请客服确认后再派单')


def record(order_id, data, actor):
    from .dispatch import get_order

    with transaction() as cur:
        order = get_order(cur, order_id, lock=True)
        require_received(order)
        prior = clearance(cur, order_id)
        if prior and (prior['status'], prior['entry_method'], prior['instructions']) == (
                data.status, data.entry_method, data.note):
            return prior
        cur.execute('''INSERT INTO order_access_clearances(order_id,status,entry_method,instructions,updated_by)
                    VALUES (%s,%s,%s,%s,%s) AS incoming ON DUPLICATE KEY UPDATE status=incoming.status,
                    entry_method=incoming.entry_method,instructions=incoming.instructions,updated_by=incoming.updated_by''',
                    (order_id, data.status, data.entry_method, data.note, actor))
        audit(cur, actor, 'access_recorded', order['code'], previous_status=prior and prior['status'],
              status=data.status, entry_method=data.entry_method, instructions=data.note)
        return clearance(cur, order_id)
