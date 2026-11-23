import json
import logging
import time
from pathlib import Path

from fastapi import HTTPException

from .db import audit, cache, transaction
from .dispatch import get_order, get_technician, require_qualification
from .feature_model import ModelUnavailable, fit

HEARTBEAT = Path('/run/dispatch/worker')
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('dispatch-worker')


def consume():
    with transaction() as cur:
        cur.execute("""SELECT id,order_id FROM dispatch_plans WHERE status='queued' ORDER BY id LIMIT 1""")
        job = cur.fetchone()
        if not job:
            return False
        # Match the order-first lock order used by dispatch and appointment edits.
        order = get_order(cur, job['order_id'], lock=True)
        cur.execute("SELECT technician_id,status FROM dispatch_plans WHERE id=%s FOR UPDATE", (job['id'],))
        locked = cur.fetchone()
        if not locked or locked['status'] != 'queued':
            return False
        technician = get_technician(cur, locked['technician_id'])
        try:
            require_qualification(order, technician)
            cur.execute('''SELECT o.id,o.service_date,o.area_m2,o.dirt_level,o.obstacles,o.supplies,
              p.experience_at_assignment AS experience_years,
              p.actual_minutes
              FROM service_orders o JOIN dispatch_plans p ON p.order_id=o.id
              WHERE o.service=%s AND o.status='followed_up' AND p.status='closed' AND p.actual_minutes IS NOT NULL
                AND p.experience_at_assignment IS NOT NULL
                AND o.service_date<%s ORDER BY o.service_date DESC,o.id DESC LIMIT 2000''',
                        (order['service'], order['service_date']))
            history = list(reversed(cur.fetchall()))
            analysis = fit(history, order, technician)
        except (ModelUnavailable, HTTPException) as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            cur.execute("UPDATE dispatch_plans SET status='failed',error_message=%s WHERE id=%s", (detail, job['id']))
            audit(cur, 'worker', 'analysis_failed', order['code'], plan_id=job['id'], detail=detail)
        else:
            cur.execute("UPDATE dispatch_plans SET status='analyzed',analysis=%s WHERE id=%s",
                        (json.dumps(analysis), job['id']))
            audit(cur, 'worker', 'analysis_ready', order['code'], plan_id=job['id'],
                  evidence=analysis['history_checksum'], selected=[f['key'] for f in analysis['features'] if f['selected']])
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
