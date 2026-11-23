import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from time import time

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pymysql import MySQLError
from redis.exceptions import RedisError

from . import dispatch, intake, rules, scheduling
from .db import audit, cache, today, transaction
from .field_routes import router as field_router
from .migrations import initialize_schema
from .models import Role, Service
from .schemas import (AnalysisRequest, Followup, Login, NewOrder, Renewal, Review, RuleComparison,
                      RuleEnable, TimeOff, VisitContact)
from .security import current_user, hash_password, issue_token, permits, verify_password


@asynccontextmanager
async def lifespan(_app):
    scheduling.initialize()
    initialize_schema()
    yield


app = FastAPI(title='栖里家服 · 派单工作台', lifespan=lifespan)
api = APIRouter()
logger = logging.getLogger('uvicorn.error')
DUMMY_HASH = hash_password('unused local password')


@app.middleware('http')
async def request_id(request: Request, call_next):
    response = await call_next(request)
    response.headers['X-Request-ID'] = secrets.token_hex(8)
    return response


@app.middleware('http')
async def no_cache(request: Request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@app.exception_handler(MySQLError)
@app.exception_handler(RedisError)
async def dependency_error(_request, exc):
    logger.error('Dispatch dependency failed', exc_info=exc)
    return JSONResponse(status_code=503, content={'detail': '存储暂不可用，请稍后重试'})


@api.get('/health')
def health():
    with transaction() as cur:
        cur.execute('SELECT 1 FROM dispatch_plans LIMIT 1')
    cache.ping()
    return {'ready': True}


@api.get('/session')
def session(user=Depends(current_user)):
    heartbeat = Path('/run/dispatch/worker')
    try:
        worker_ready = time() - heartbeat.stat().st_mtime < 10
    except FileNotFoundError:
        worker_ready = False
    return {'name': user['name'], 'role': user['role'], 'business_date': today(), 'worker_ready': worker_ready}


@api.post('/login')
def login(data: Login):
    username = data.username.lower()
    key = f'login:{username}'
    attempts = cache.eval("local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],60) end; return n", 1, key)
    if attempts > 12:
        raise HTTPException(429, '登录尝试过多，请一分钟后重试')
    with transaction() as cur:
        cur.execute('SELECT username,display_name,role,password_hash FROM users WHERE username=%s', (username,))
        user = cur.fetchone()
        if not verify_password(data.password, user['password_hash'] if user else DUMMY_HASH) or not user:
            raise HTTPException(401, '账号或密码不正确')
        audit(cur, user['username'], 'login', user['username'], subject_kind='user')
    cache.delete(key)
    return {'token': issue_token(user)}


@api.get('/orders')
def list_orders(_user=Depends(current_user)):
    return intake.orders()


@api.post('/orders', status_code=201)
def new_order(data: NewOrder, user=Depends(permits(Role.INTAKE))):
    return intake.create_order(data, user['sub'])


@api.get('/technicians')
def list_technicians(_user=Depends(current_user)):
    return intake.technicians()


@api.put('/technicians/{technician_id}/qualification')
def renew_qualification(technician_id: int, data: Renewal, user=Depends(permits(Role.SUPERVISOR))):
    return intake.renew_qualification(technician_id, data, user['sub'])


@api.get('/plans')
def list_plans(_user=Depends(current_user)):
    return dispatch.plans()


@api.get('/plans/{plan_id}')
def plan_details(plan_id: int, _user=Depends(current_user)):
    with transaction() as cur:
        return dispatch.get_plan(cur, plan_id)


@api.post('/orders/{order_id}/analysis', status_code=202)
def analyze(order_id: int, data: AnalysisRequest, user=Depends(permits(Role.DISPATCHER))):
    return dispatch.queue_analysis(order_id, data.technician_id, user['sub'])


@api.post('/plans/{plan_id}/trial')
def trial(plan_id: int, user=Depends(permits(Role.DISPATCHER))):
    return dispatch.run_trial(plan_id, user['sub'])


@api.post('/plans/{plan_id}/confirm')
def confirm(plan_id: int, user=Depends(permits(Role.DISPATCHER))):
    return dispatch.confirm(plan_id, user['sub'])


@api.post('/plans/{plan_id}/followup')
def followup(plan_id: int, data: Followup, user=Depends(permits(Role.INTAKE))):
    return dispatch.record_followup(plan_id, data, user['sub'])


@api.post('/plans/{plan_id}/review')
def review(plan_id: int, data: Review, user=Depends(permits(Role.SUPERVISOR))):
    return dispatch.approve_review(plan_id, data.note, user['sub'])


@api.get('/orders/{order_id}/events')
def order_events(order_id: int, _user=Depends(current_user)):
    with transaction() as cur:
        order = dispatch.get_order(cur, order_id)
        cur.execute("""SELECT actor,event,details,happened_at FROM audit_events
          WHERE subject_kind='order' AND subject=%s ORDER BY id""",
                    (order['code'],))
        return cur.fetchall()


@api.get('/feature-rules/{service}')
def feature_rules(service: Service, _user=Depends(current_user)):
    with transaction() as cur:
        return rules.list_for_service(cur, service)


@api.post('/feature-rules/{service}/comparisons', status_code=201)
def compare_feature_rules(service: Service, data: RuleComparison, user=Depends(permits(Role.DISPATCHER))):
    return rules.compare(service, data, user['sub'])


@api.post('/feature-rules/comparisons/{comparison_id}/enable')
def enable_feature_rules(comparison_id: int, data: RuleEnable, user=Depends(permits(Role.SUPERVISOR))):
    return rules.enable(comparison_id, data, user['sub'])


@api.get('/time-off')
def time_offs(_user=Depends(current_user)):
    return scheduling.time_offs()


@api.post('/time-off', status_code=201)
def add_time_off(data: TimeOff, user=Depends(permits(Role.SUPERVISOR))):
    return scheduling.add_time_off(data, user['sub'])


@api.delete('/time-off/{identifier}', status_code=204)
def remove_time_off(identifier: int, user=Depends(permits(Role.SUPERVISOR))):
    scheduling.remove_time_off(identifier, user['sub'])


@api.get('/visit-contacts')
def contacts(_user=Depends(current_user)):
    return scheduling.contacts()


@api.post('/orders/{order_id}/visit-contacts', status_code=201)
def record_contact(order_id: int, data: VisitContact, user=Depends(permits(Role.INTAKE))):
    return scheduling.record_contact(order_id, data, user['sub'])


app.include_router(api)
app.include_router(field_router)
