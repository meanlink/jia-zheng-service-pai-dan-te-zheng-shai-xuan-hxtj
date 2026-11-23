import json
from pathlib import Path

from .db import transaction
from .feature_model import FEATURES

MIGRATIONS = ('002_fieldwork.sql', '003_feature_rules.sql')


def _apply(cur, name):
    migration = Path(__file__).resolve().parents[1] / 'migrations' / name
    for statement in migration.read_text(encoding='utf-8').split(';'):
        if statement.strip():
            cur.execute(statement)


def _ensure_column(cur, table, column, definition):
    cur.execute('''SELECT 1 FROM information_schema.columns
                   WHERE table_schema=DATABASE() AND table_name=%s AND column_name=%s''', (table, column))
    if not cur.fetchone():
        cur.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')


def _ensure_subject_kind(cur):
    """Audit rows for category rule changes need their own subject kind."""
    cur.execute('''SELECT column_type FROM information_schema.columns
                   WHERE table_schema=DATABASE() AND table_name='audit_events' AND column_name='subject_kind' ''')
    row = cur.fetchone()
    if row and 'category' not in row['column_type']:
        cur.execute('''ALTER TABLE audit_events MODIFY COLUMN subject_kind
                       ENUM('order','technician','user','category') NOT NULL''')


def _seed_default_rules(cur):
    for service in ('deep_clean', 'appliance_clean'):
        cur.execute('SELECT id FROM category_feature_rules WHERE service=%s AND active=1 LIMIT 1', (service,))
        if cur.fetchone():
            continue
        cur.execute('''INSERT INTO category_feature_rules(service,version,features,active,created_by)
                       VALUES (%s,1,%s,1,'system')''', (service, json.dumps(list(FEATURES))))


def _backfill_queued_rules(cur):
    """Plans queued before per-category rules existed still belong to the rule
    that was active when this schema upgrade runs, before any later switch."""
    cur.execute('''SELECT p.id,o.service FROM dispatch_plans p JOIN service_orders o ON o.id=p.order_id
                   WHERE p.status=%s AND p.feature_rule IS NULL''', ('queued',))
    plans = cur.fetchall()
    for plan in plans:
        cur.execute('''SELECT id,version,features FROM category_feature_rules
                       WHERE service=%s AND active=1 ORDER BY version DESC LIMIT 1''', (plan['service'],))
        rule = cur.fetchone()
        if not rule:
            continue
        snapshot = {'id': rule['id'], 'version': rule['version'],
                    'features': json.loads(rule['features']), 'fallback': None}
        cur.execute('UPDATE dispatch_plans SET feature_rule=%s WHERE id=%s',
                    (json.dumps(snapshot), plan['id']))


def initialize_schema():
    """Apply additive DDL to both fresh databases and existing dispatch volumes."""
    with transaction() as cur:
        for name in MIGRATIONS:
            _apply(cur, name)
        _ensure_subject_kind(cur)
        # Queued plans keep the rule that was active when they were submitted.
        _ensure_column(cur, 'dispatch_plans', 'feature_rule', 'JSON NULL')
        _seed_default_rules(cur)
        _backfill_queued_rules(cur)


def initialize_fieldwork():
    """Backward-compatible entry point used by the demo seed."""
    initialize_schema()
