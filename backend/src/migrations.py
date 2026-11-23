from pathlib import Path

from .db import transaction


def initialize_fieldwork():
    """Apply additive DDL to both fresh databases and existing dispatch volumes."""
    migration = Path(__file__).resolve().parents[1] / 'migrations' / '002_fieldwork.sql'
    with transaction() as cur:
        for statement in migration.read_text(encoding='utf-8').split(';'):
            if statement.strip():
                cur.execute(statement)
