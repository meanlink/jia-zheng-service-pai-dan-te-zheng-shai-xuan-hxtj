import json


def seed_fieldwork(cur, day):
    cur.execute('''INSERT INTO service_orders(code,customer,neighborhood,service,service_date,slot,
                    area_m2,dirt_level,obstacles,supplies,baseline_minutes)
                    VALUES ('QL-1105','罗女士','长宁 · 天山路','deep_clean',%s,'am',92,3,2,1,145)
                    ON DUPLICATE KEY UPDATE id=id''', (day,))
    cur.execute("SELECT id FROM service_orders WHERE code='QL-1105'")
    order_id = cur.fetchone()['id']
    original = {'area_m2': 92, 'dirt_level': 3, 'obstacles': 2, 'supplies': True}
    cur.execute('''INSERT INTO order_scope_revisions(order_id,revision_no,previous_scope,area_m2,dirt_level,
                    obstacles,supplies,reason,submitted_by) VALUES (%s,1,%s,104,4,3,0,%s,'intake')
                    ON DUPLICATE KEY UPDATE id=id''',
                (order_id, json.dumps(original), '客户补发阳台照片，确认阳台计入面积且现场无耗材。'))
    cur.execute('''INSERT INTO order_access_clearances(order_id,status,entry_method,instructions,updated_by)
                    VALUES (%s,'blocked','concierge',%s,'intake') ON DUPLICATE KEY UPDATE order_id=order_id''',
                (order_id, '物业尚未完成访客报备，客户需在工作台确认放行。'))
