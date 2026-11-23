import json

from fastapi import HTTPException

from .db import audit, transaction
from .feature_model import ModelUnavailable, estimate
from .models import PlanStatus
from .scope import SCOPE_FIELDS, current_scope, require_received

COMPARABLE = (PlanStatus.ANALYZED, PlanStatus.TRIAL, PlanStatus.REVIEW_PRE, PlanStatus.REVIEWED)


def analysis_event(cur, order, plan):
    if not plan or not plan['analysis']:
        return None
    cur.execute('''SELECT id FROM audit_events WHERE subject_kind='order' AND subject=%s
                   AND event='analysis_ready' ORDER BY id DESC LIMIT 1''', (order['code'],))
    row = cur.fetchone()
    return row['id'] if row else None


def list_for_order(cur, order, plan):
    event_id = analysis_event(cur, order, plan)
    rows = []
    if plan:
        cur.execute('SELECT * FROM dispatch_scenarios WHERE plan_id=%s ORDER BY id DESC LIMIT 30', (plan['id'],))
        for row in cur.fetchall():
            row['comparison'] = json.loads(row['comparison'])
            row['current'] = row['analysis_event_id'] == event_id
            rows.append(row)
    return {'analysis_event_id': event_id, 'can_compare': bool(event_id and plan['status'] in COMPARABLE),
            'scenarios': rows}


def compare(analysis, revised):
    features = []
    for feature in analysis['features']:
        key = feature['key']
        value = float(revised.get(key, feature['value']))
        contribution = feature['coefficient'] * (value - feature['training_mean'])
        low, high = feature.get('training_min'), feature.get('training_max')
        features.append({**feature, 'value': value, 'contribution': contribution,
                         'outside_history': feature['outside_history'] if value == feature['value'] else
                         (not low <= value <= high if low is not None and high is not None else None)})
    return features


def save(plan_id, data, actor):
    from .dispatch import lock_plan_and_order, require_status

    with transaction() as cur:
        plan, order = lock_plan_and_order(cur, plan_id)
        require_received(order)
        require_status(plan, *COMPARABLE)
        event_id = analysis_event(cur, order, plan)
        if event_id != data.analysis_event_id:
            raise HTTPException(409, '模型版本已变化，请刷新后重新对照')
        revised = data.model_dump(include=set(SCOPE_FIELDS))
        if revised == current_scope(order):
            raise HTTPException(422, '至少修改一项假设条件')
        analysis = plan['analysis']
        features = compare(analysis, revised)
        try:
            baseline = estimate(analysis)
            alternative = estimate({**analysis, 'features': features})
        except ModelUnavailable as exc:
            raise HTTPException(422, str(exc)) from exc
        comparison = {
            'baseline_minutes': baseline, 'scenario_minutes': alternative, 'delta_minutes': alternative - baseline,
            'history_checksum': analysis['history_checksum'], 'holdout_mae': analysis['holdout_mae'],
            'features': [{
                'key': previous['key'], 'selected': previous['selected'], 'before': previous['value'],
                'after': proposed['value'], 'contribution_delta': proposed['contribution'] - previous['contribution'],
                'outside_history': proposed['outside_history'],
            } for previous, proposed in zip(analysis['features'], features)],
        }
        cur.execute('''INSERT INTO dispatch_scenarios(plan_id,analysis_event_id,creator,note,comparison)
                       VALUES (%s,%s,%s,%s,%s)''', (plan_id, event_id, actor, data.note, json.dumps(comparison)))
        scenario_id = cur.lastrowid
        audit(cur, actor, 'scenario_saved', order['code'], scenario_id=scenario_id,
              model=event_id, delta_minutes=comparison['delta_minutes'])
        return {'id': scenario_id, 'comparison': comparison}
