import json
import logging
import time
from pathlib import Path

from fastapi import HTTPException

from . import rules
from .db import audit, cache, transaction
from .dispatch import get_order, get_technician, require_qualification
from .feature_model import ModelUnavailable, fit

HEARTBEAT = Path('/run/dispatch/worker')
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('dispatch-worker')


def queued_rule(cur, plan, order):
    """Return the rule snapshot taken when this plan was queued.

    A plan queued before per-category rules existed has no snapshot; it is
    pinned to the categories' current rule now so later switches cannot
    change what an already-queued analysis computes."""
    if plan.get('feature_rule'):
        return json.loads(plan['feature_rule'])
    snapshot = rules.snapshot(cur, order['service'])
    cur.execute('UPDATE dispatch_plans SET feature_rule=%s WHERE id=%s',
                (json.dumps(snapshot), plan['id']))
    return snapshot


def fit_with_rule(history, order, technician, rule):
    """Fit the queued rule. If the new feature group cannot be solved, fall
    back to the rule it replaced so the category does not lose coverage."""
    try:
        analysis = fit(history, order, technician, rule['features'])
        analysis['rule'] = {'id': rule['id'], 'version': rule['version'], 'features': rule['features']}
        return analysis
    except ModelUnavailable as exc:
        fallback = rule.get('fallback')
        if not fallback:
            raise
        analysis = fit(history, order, technician, fallback['features'])
        analysis['rule'] = {'id': fallback['id'], 'version': fallback['version'],
                            'features': fallback['features']}
        analysis['rule_fallback'] = {'from_version': rule['version'], 'from_features': rule['features'],
                                     'reason': str(exc)}
        return analysis


def consume():
    with transaction() as cur:
        cur.execute("""SELECT id,order_id,feature_rule FROM dispatch_plans
                       WHERE status='queued' ORDER BY id LIMIT 1""")
        job = cur.fetchone()
        if not job:
            return False
        # Match the order-first lock order used by dispatch and appointment edits.
        order = get_order(cur, job['order_id'], lock=True)
        cur.execute("SELECT technician_id,status,feature_rule FROM dispatch_plans WHERE id=%s FOR UPDATE", (job['id'],))
        locked = cur.fetchone()
        if not locked or locked['status'] != 'queued':
            return False
        technician = get_technician(cur, locked['technician_id'])
        try:
            require_qualification(order, technician)
            rule = queued_rule(cur, {**job, **locked}, order)
            batch = rules.history(cur, order['service'], order['service_date'])
            analysis = fit_with_rule(batch, order, technician, rule)
        except (ModelUnavailable, HTTPException) as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            cur.execute("UPDATE dispatch_plans SET status='failed',error_message=%s WHERE id=%s", (detail, job['id']))
            audit(cur, 'worker', 'analysis_failed', order['code'], plan_id=job['id'], detail=detail)
        else:
            cur.execute("UPDATE dispatch_plans SET status='analyzed',analysis=%s WHERE id=%s",
                        (json.dumps(analysis), job['id']))
            audit(cur, 'worker', 'analysis_ready', order['code'], plan_id=job['id'],
                  evidence=analysis['history_checksum'],
                  selected=[f['key'] for f in analysis['features'] if f['selected']],
                  rule_version=analysis['rule']['version'], rule_features=analysis['rule']['features'],
                  rule_fallback=analysis.get('rule_fallback'))
        logger.info('Processed order %s, plan #%s', order['code'], job['id'])
        return True


def main():
    while True:
        try:
            cache.ping()
            worked = consume()
            HEARTBEAT.touch()
        except Exception:
            logger.exception('Queue iteration failed; current transaction rolled back')
            worked = False
        if not worked:
            time.sleep(1)


if __name__ == '__main__':
    main()
