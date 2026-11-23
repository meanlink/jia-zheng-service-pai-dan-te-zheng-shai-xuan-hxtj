import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

import pymysql
from redis import Redis

SHANGHAI = ZoneInfo('Asia/Shanghai')
cache = Redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379/0'), socket_timeout=2)


def today():
    return datetime.now(SHANGHAI).date()


@contextmanager
def transaction() -> Iterator:
    conn = pymysql.connect(
        host=os.getenv('DB_HOST', 'localhost'), port=int(os.getenv('MYSQL_PORT', '3306')),
        user='dispatch', password=os.environ['DB_PASSWORD'], database='dispatch',
        charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor,
        init_command='SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED',
        connect_timeout=4, read_timeout=9, write_timeout=9,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SET time_zone = '+08:00'")
            yield cur
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def audit(cur, actor, event, subject, *, subject_kind='order', **details):
    cur.execute(
        'INSERT INTO audit_events(actor,event,subject_kind,subject,details) VALUES (%s,%s,%s,%s,%s)',
        (actor, event, subject_kind, subject, json.dumps(details, ensure_ascii=False, default=str)),
    )
