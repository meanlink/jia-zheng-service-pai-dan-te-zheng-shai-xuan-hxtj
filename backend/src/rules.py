import json

from fastapi import HTTPException

from .db import audit, transaction
from .feature_model import (FEATURES, HIGH_DIRT_LEVEL, MIN_HIGH_DIRT_SAMPLES, ModelUnavailable,
                            evaluate)

HISTORY_LIMIT = 2000
HISTORY_SQL = '''SELECT o.id,o.service_date,o.area_m2,o.dirt_level,o.obstacles,o.supplies,
  p.experience_at_assignment AS experience_years,p.actual_minutes
  FROM service_orders o JOIN dispatch_plans p ON p.order_id=o.id
  WHERE o.service=%s AND o.status='followed_up' AND p.status='closed' AND p.actual_minutes IS NOT NULL
    AND p.experience_at_assignment IS NOT NULL
  ORDER BY o.service_date DESC,o.id DESC LIMIT %s'''


def history(cur, service, before_date=None):
    """One ordered batch of closed同类 orders. Rule comparisons and the worker
    evaluate exactly this batch so two rules see the same rows and split."""
    if before_date is None:
        cur.execute(HISTORY_SQL, (service, HISTORY_LIMIT))
    else:
        cur.execute(HISTORY_SQL.replace("o.status='followed_up'",
                                        "o.status='followed_up' AND o.service_date<%s"),
                    (service, before_date, HISTORY_LIMIT))
    return list(reversed(cur.fetchall()))


def _rule_row(row):
    if row:
        row['features'] = json.loads(row['features'])
    return row


def active_rule(cur, service, *, lock=False):
    suffix = ' FOR UPDATE' if lock else ''
    cur.execute(f'''SELECT * FROM category_feature_rules WHERE service=%s AND active=1
                    ORDER BY version DESC LIMIT 1{suffix}''', (service,))
    return _rule_row(cur.fetchone())


def _rule(row):
    return {'id': row['id'], 'version': row['version'], 'features': row['features']}


def snapshot(cur, service):
    """Capture the rule used by one queued analysis. Queued work keeps this
    snapshot even if the supervisor switches the category rule afterwards.
    The replaced rule travels with it so a fit that fails under the new
    feature group can fall back instead of leaving the order unanalyzable."""
    rule = active_rule(cur, service)
    if not rule:
        raise HTTPException(503, '该品类尚未设定特征规则')
    fallback = None
    if rule['previous_rule_id']:
        cur.execute('SELECT * FROM category_feature_rules WHERE id=%s', (rule['previous_rule_id'],))
        previous = _rule_row(cur.fetchone())
        if previous and previous['features'] != rule['features']:
            fallback = {'id': previous['id'], 'version': previous['version'],
                        'features': previous['features']}
    return {'id': rule['id'], 'version': rule['version'], 'features': rule['features'],
            'fallback': fallback}


def _comparison(row):
    if not row:
        return None
    row['candidate_features'] = json.loads(row['candidate_features'])
    row['baseline'] = json.loads(row['baseline'])
    row['candidate'] = json.loads(row['candidate'])
    return row


def _complete(row):
    """Rows without both error readings cannot be shown or enabled; skip them
    instead of presenting a half-filled comparison."""
    return all(row[side].get('holdout_mae') is not None and row[side].get('features')
               for side in ('baseline', 'candidate'))

def list_for_service(cur, service):
    rule = active_rule(cur, service)
    cur.execute('''SELECT * FROM feature_rule_comparisons WHERE service=%s
                   ORDER BY id DESC LIMIT 20''', (service,))
    comparisons = [row for row in (_comparison(item) for item in cur.fetchall()) if _complete(row)]
    batch = history(cur, service)
    if batch:
        split = batch[int(len(batch) * 0.8)]['service_date']
        heavy = sum(row['dirt_level'] >= HIGH_DIRT_LEVEL for row in batch if row['service_date'] >= split)
        holdout = sum(row['service_date'] >= split for row in batch)
    else:
        split, heavy, holdout = None, 0, 0
    return {
        'service': service,
        'active_rule': _rule(rule) if rule else None,
        'comparisons': comparisons,
        'history_count': len(batch),
        'holdout_count': holdout,
        'holdout_high_dirt_count': heavy,
        'holdout_since': str(split) if split else None,
        'min_high_dirt_samples': MIN_HIGH_DIRT_SAMPLES,
        'features': list(FEATURES),
        'can_compare': bool(rule),
    }


def _eligibility(baseline, candidate):
    if candidate['high_dirt_count'] < MIN_HIGH_DIRT_SAMPLES or \
            baseline['high_dirt_count'] < MIN_HIGH_DIRT_SAMPLES or \
            candidate['high_dirt_mae'] is None or baseline['high_dirt_mae'] is None:
        return 'insufficient'
    if candidate['holdout_mae'] <= baseline['holdout_mae'] and \
            candidate['high_dirt_mae'] <= baseline['high_dirt_mae']:
        return 'pass'
    return 'regression'


def _verified(row):
    """Re-read the two error readings from the stored comparison instead of
    trusting the eligibility flag written when it was created."""
    if not _complete(row):
        raise HTTPException(409, '该对照缺少完整的误差记录，请重新对照')
    if row['baseline']['history_checksum'] != row['candidate']['history_checksum'] or \
            row['baseline']['holdout_since'] != row['candidate']['holdout_since'] or \
            row['history_checksum'] != row['candidate']['history_checksum']:
        raise HTTPException(409, '该对照未使用同一批完单与同一时间切分，请重新对照')
    eligibility = _eligibility(row['baseline'], row['candidate'])
    if eligibility != row['eligibility']:
        raise HTTPException(409, '该对照的误差结论与记录不一致，请重新对照')
    return eligibility


def compare(service, data, actor):
    """Score one candidate feature set against the current rule on the same
    completed orders and the same fixed-date split. Nothing is switched yet."""
    with transaction() as cur:
        rule = active_rule(cur, service, lock=True)
        if not rule:
            raise HTTPException(409, '该品类尚无现行特征规则，不能对照')
        features = list(data.features)
        if sorted(features) == sorted(rule['features']):
            raise HTTPException(422, '候选特征与现行规则相同，请调整后重新对照')
        batch = history(cur, service)
        try:
            baseline = evaluate(batch, rule['features'])
            candidate = evaluate(batch, features)
        except ModelUnavailable as exc:
            raise HTTPException(422, str(exc)) from exc
        if baseline['history_checksum'] != candidate['history_checksum'] or \
                baseline['holdout_since'] != candidate['holdout_since']:
            raise HTTPException(409, '两次拟合未使用同一批完单与同一时间切分，请重试')
        baseline['rule_version'] = rule['version']
        eligibility = _eligibility(baseline, candidate)
        cur.execute('''INSERT INTO feature_rule_comparisons(service,baseline_rule_id,candidate_features,
                       baseline,candidate,history_checksum,holdout_since,eligibility,note,created_by)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                    (service, rule['id'], json.dumps(features), json.dumps(baseline), json.dumps(candidate),
                     candidate['history_checksum'], candidate['holdout_since'], eligibility, data.note, actor))
        comparison_id = cur.lastrowid
        audit(cur, actor, 'feature_rule_compared', service, subject_kind='category',
              comparison_id=comparison_id, candidate=features, baseline_rule=rule['version'],
              baseline_mae=baseline['holdout_mae'], candidate_mae=candidate['holdout_mae'],
              baseline_high_dirt_mae=baseline['high_dirt_mae'],
              candidate_high_dirt_mae=candidate['high_dirt_mae'], eligibility=eligibility)
        cur.execute('SELECT * FROM feature_rule_comparisons WHERE id=%s', (comparison_id,))
        return _comparison(cur.fetchone())


def enable(comparison_id, data, actor):
    """Atomically switch one category to the candidate feature set.

    Enabling re-checks the rule that is current inside the lock. If another
    supervisor already switched it, this comparison is stale and must be redone
    against the new current rule instead of silently overwriting it."""
    with transaction() as cur:
        cur.execute('SELECT * FROM feature_rule_comparisons WHERE id=%s FOR UPDATE', (comparison_id,))
        comparison = _comparison(cur.fetchone())
        if not comparison:
            raise HTTPException(404, '特征规则对照不存在')
        if comparison['enabled']:
            raise HTTPException(409, '该对照已启用，无需重复操作')
        service = comparison['service']
        rule = active_rule(cur, service, lock=True)
        if not rule or comparison['baseline_rule_id'] != rule['id']:
            raise HTTPException(409, '现行规则已更换，请按新的现行规则重新对照后再启用')
        eligibility = _verified(comparison)
        if eligibility == 'insufficient':
            raise HTTPException(409, '高污损单验证样本不足，暂缓启用该特征组')
        if eligibility != 'pass':
            raise HTTPException(409, '候选特征在总体或高污损单上的误差变大，不能启用')
        if comparison['candidate_features'] == rule['features']:
            raise HTTPException(409, '候选特征已与现行规则一致，无需重复启用')
        cur.execute('SELECT COALESCE(MAX(version),0)+1 AS version FROM category_feature_rules WHERE service=%s',
                    (service,))
        version = cur.fetchone()['version']
        cur.execute('''INSERT INTO category_feature_rules(service,version,features,active,created_by,previous_rule_id)
                       VALUES (%s,%s,%s,1,%s,%s)''',
                    (service, version, json.dumps(comparison['candidate_features']), actor, rule['id']))
        new_rule_id = cur.lastrowid
        cur.execute('UPDATE category_feature_rules SET active=0 WHERE id=%s', (rule['id'],))
        cur.execute('''UPDATE feature_rule_comparisons SET enabled=1,enabled_rule_id=%s,enabled_by=%s,
                       enabled_at=CURRENT_TIMESTAMP WHERE id=%s''',
                    (new_rule_id, actor, comparison_id))
        audit(cur, actor, 'feature_rule_enabled', service, subject_kind='category',
              comparison_id=comparison_id, rule_id=new_rule_id, version=version,
              features=comparison['candidate_features'], replaced_rule=rule['version'], note=data.note)
        cur.execute('SELECT * FROM category_feature_rules WHERE id=%s', (new_rule_id,))
        return _rule(_rule_row(cur.fetchone()))
