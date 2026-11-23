import json

from fastapi import HTTPException

from .access import clearance
from .db import audit, today, transaction
from .models import PlanStatus
from .scope import current_scope


def list_for_plan(cur, plan_id, *, latest_only=False):
    limit = 1 if latest_only else 30
    cur.execute('SELECT * FROM visit_handover_briefs WHERE plan_id=%s ORDER BY edition DESC LIMIT %s', (plan_id, limit))
    rows = cur.fetchall()
    for row in rows:
        row['snapshot'] = json.loads(row['snapshot'])
    return rows


def require_arrival(cur, plan_id):
    rows = list_for_plan(cur, plan_id, latest_only=True)
    if rows and rows[0]['status'] != 'arrived':
        raise HTTPException(409, '当前上门交接尚未确认到场，不能登记完工回访')


def issue(plan_id, data, actor):
    from .dispatch import get_technician, lock_plan_and_order, require_status

    with transaction() as cur:
        plan, order = lock_plan_and_order(cur, plan_id)
        require_status(plan, PlanStatus.CONFIRMED)
        rows = list_for_plan(cur, plan_id, latest_only=True)
        prior = rows[0] if rows else None
        if prior and prior['status'] != 'access_failed':
            raise HTTPException(409, '本次上门已有交接单，只有入户失败才可补发')
        if prior and data.correction is None:
            raise HTTPException(422, '补发交接单须填写新的入户安排')
        if not prior and data.correction is not None:
            raise HTTPException(422, '首次交接采用派前核验的入户安排')
        tech = get_technician(cur, plan['technician_id'])
        access = clearance(cur, order['id'])
        entry = access['entry_method'] if access else None
        instructions = access['instructions'] if access else None
        if data.correction:
            entry, instructions = data.correction.entry_method, data.correction.entry_instructions
            if (entry, instructions) == (prior['snapshot']['entry'], prior['snapshot']['entry_instructions']):
                raise HTTPException(422, '补发交接单须变更当前入户安排')
        snapshot = {'order_code': order['code'], 'neighborhood': order['neighborhood'],
                    'service': order['service'], 'service_date': str(order['service_date']), 'slot': order['slot'],
                    'technician': tech['name'], 'estimated_minutes': plan['predicted_minutes'],
                    'scope': current_scope(order), 'entry': entry, 'entry_instructions': instructions}
        edition = prior['edition'] + 1 if prior else 1
        cur.execute('''INSERT INTO visit_handover_briefs(plan_id,edition,snapshot,instructions,issued_by)
                       VALUES (%s,%s,%s,%s,%s)''', (plan_id, edition, json.dumps(snapshot), data.note, actor))
        audit(cur, actor, 'handover_issued', order['code'], plan_id=plan_id, edition=edition)
        return list_for_plan(cur, plan_id, latest_only=True)[0]


def arrival(plan_id, brief_id, data, actor):
    from .dispatch import lock_plan_and_order, require_status

    with transaction() as cur:
        plan, order = lock_plan_and_order(cur, plan_id)
        require_status(plan, PlanStatus.CONFIRMED)
        rows = list_for_plan(cur, plan_id, latest_only=True)
        if not rows or rows[0]['id'] != brief_id or rows[0]['status'] != 'issued':
            raise HTTPException(409, '仅可登记当前待回执的交接单')
        if order['service_date'] > today():
            raise HTTPException(409, '预约日期尚未到达，无法登记到场回执')
        cur.execute('''UPDATE visit_handover_briefs SET status=%s,arrival_note=%s,arrival_by=%s,
                       arrival_at=CURRENT_TIMESTAMP WHERE id=%s''', (data.status, data.note, actor, brief_id))
        audit(cur, actor, 'handover_arrival', order['code'], plan_id=plan_id, edition=rows[0]['edition'], status=data.status)
        return list_for_plan(cur, plan_id, latest_only=True)[0]
