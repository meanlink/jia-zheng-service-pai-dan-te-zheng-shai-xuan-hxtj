from datetime import timedelta
from random import Random

from src.db import today, transaction
from src.migrations import initialize_fieldwork
from scripts.seed_fieldwork import seed_fieldwork
from src.security import hash_password

PASSWORD = 'Qili-demo-48'
TECHNICIANS = [
    ('QL-T01', '周兰', 'deep_clean', 'SH-QJ-0186', 220, 8),
    ('QL-T02', '姚宁', 'deep_clean', 'SH-QJ-0261', -3, 4),
    ('QL-T03', '陈师傅', 'deep_clean', 'SH-QJ-0328', 90, 2),
    ('QL-T04', '林涛', 'appliance_clean', 'SH-JD-1105', 170, 7),
    ('QL-T05', '郑师傅', 'appliance_clean', 'SH-JD-1210', 3, 3),
]
LIVE = [
    ('QL-1101', '许女士', '杨浦 · 控江路', 'deep_clean', 'am', 86, 3, 2, True, 120),
    ('QL-1102', '沈先生', '虹口 · 曲阳路', 'deep_clean', 'pm', 142, 5, 5, False, 75),
    ('QL-1103', '丁女士', '静安 · 大宁路', 'appliance_clean', 'evening', 38, 4, 2, True, 95),
    ('QL-1104', '任先生', '普陀 · 长寿路', 'deep_clean', 'evening', 72, 2, 1, True, 95),
]


def seed_history(cur, day, technicians):
    rng = Random(1048)
    for prefix, skill, tech_codes in [('C', 'deep_clean', ['QL-T01', 'QL-T02', 'QL-T03']),
                                       ('A', 'appliance_clean', ['QL-T04', 'QL-T05'])]:
        for i in range(84):
            tech = technicians[rng.choice(tech_codes)]
            area = rng.randint(35, 158) if prefix == 'C' else rng.randint(18, 65)
            dirt, obstacles, supplies = rng.randint(1, 5), rng.randint(0, 6), rng.choice([True, False])
            # Obstacles and on-site supplies are weak signals in this sample.
            actual = round(36 + 0.75 * area + 14 * dirt - 3.4 * tech['experience_years'] + rng.gauss(0, 5))
            actual = max(15, actual)
            code = f'QL-H{prefix}-{i + 1:03d}'
            date = day - timedelta(days=44 - i // 2)
            cur.execute('''INSERT INTO service_orders(code,customer,neighborhood,service,service_date,slot,
              area_m2,dirt_level,obstacles,supplies,baseline_minutes,status)
              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'followed_up') ON DUPLICATE KEY UPDATE id=id''',
                        (code, f'匿名住户 {i + 1:03d}', '上海 · 历史脱敏样本', skill, date,
                         'am' if i % 2 == 0 else 'pm', area, dirt, obstacles, supplies, max(15, actual + 3)))
            cur.execute('SELECT id FROM service_orders WHERE code=%s', (code,))
            order_id = cur.fetchone()['id']
            cur.execute('''INSERT INTO dispatch_plans(order_id,technician_id,status,predicted_minutes,
              confirm_by,experience_at_assignment,actual_minutes,followup_note)
              VALUES (%s,%s,'closed',%s,'dispatch',%s,%s,'历史完单回执')
              ON DUPLICATE KEY UPDATE id=id''', (order_id, tech['id'], max(15, actual + 2), tech['experience_years'], actual))


def main():
    initialize_fieldwork()
    day = today()
    with transaction() as cur:
        for username, name, role in [('intake', '唐宁', 'intake'), ('dispatch', '苏曼', 'dispatcher'),
                                     ('lead', '孟慧', 'supervisor')]:
            cur.execute('''INSERT INTO users(username,display_name,role,password_hash) VALUES (%s,%s,%s,%s)
              ON DUPLICATE KEY UPDATE username=username''', (username, name, role, hash_password(PASSWORD)))
        for code, name, skill, cert, offset, years in TECHNICIANS:
            cur.execute('''INSERT INTO technicians(code,name,skill,certificate,valid_through,experience_years)
              VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE id=id''',
                        (code, name, skill, cert, day + timedelta(days=offset), years))
        cur.execute('SELECT id,code,experience_years FROM technicians')
        seed_history(cur, day, {tech['code']: tech for tech in cur.fetchall()})
        for code, customer, neighborhood, skill, slot, area, dirt, obstacles, supplies, baseline in LIVE:
            cur.execute('''INSERT INTO service_orders(code,customer,neighborhood,service,service_date,slot,
              area_m2,dirt_level,obstacles,supplies,baseline_minutes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
              ON DUPLICATE KEY UPDATE id=id''', (code, customer, neighborhood, skill, day, slot,
                                                area, dirt, obstacles, supplies, baseline))
        seed_fieldwork(cur, day)
        for table in ('users', 'technicians', 'service_orders', 'dispatch_plans', 'audit_events',
                      'order_scope_revisions', 'order_access_clearances', 'dispatch_scenarios', 'visit_handover_briefs'):
            cur.execute(f'SELECT COUNT(*) AS n FROM {table}')
            print(f'{table}={cur.fetchone()["n"]}')


if __name__ == '__main__':
    main()
