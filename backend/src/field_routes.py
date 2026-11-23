from fastapi import APIRouter, Depends

from . import access, handover, scenarios, scope
from .db import transaction
from .dispatch import get_order, get_plan
from .field_schemas import AccessClearance, ArrivalReport, HandoverIssue, ScopeDecision, ScopeProposal, SensitivityScenario
from .models import Role
from .security import current_user, permits

router = APIRouter()


@router.get('/orders/{order_id}/fieldwork')
def order_fieldwork(order_id: int, _user=Depends(current_user)):
    with transaction() as cur:
        # All field mutations and analysis publication serialize on the order row.
        order = get_order(cur, order_id, lock=True)
        cur.execute('SELECT id FROM dispatch_plans WHERE order_id=%s', (order_id,))
        row = cur.fetchone()
        plan = get_plan(cur, row['id']) if row else None
        return {'order': order, 'scope': scope.latest(cur, order_id), 'access': access.clearance(cur, order_id),
                'plan_id': plan['id'] if plan else None, 'plan_status': plan['status'] if plan else None,
                **scenarios.list_for_order(cur, order, plan),
                'briefs': handover.list_for_plan(cur, plan['id']) if plan else []}


@router.post('/orders/{order_id}/scope-revisions', status_code=201)
def propose(order_id: int, data: ScopeProposal, user=Depends(permits(Role.INTAKE))):
    return scope.propose(order_id, data, user['sub'])


@router.post('/orders/{order_id}/scope-revisions/{revision_id}/decision')
def decide(order_id: int, revision_id: int, data: ScopeDecision, user=Depends(permits(Role.SUPERVISOR))):
    return scope.decide(order_id, revision_id, data, user['sub'])


@router.put('/orders/{order_id}/access')
def record_access(order_id: int, data: AccessClearance, user=Depends(permits(Role.INTAKE))):
    return access.record(order_id, data, user['sub'])


@router.post('/plans/{plan_id}/scenarios', status_code=201)
def save_scenario(plan_id: int, data: SensitivityScenario, user=Depends(permits(Role.DISPATCHER))):
    return scenarios.save(plan_id, data, user['sub'])


@router.post('/plans/{plan_id}/handover', status_code=201)
def issue_brief(plan_id: int, data: HandoverIssue, user=Depends(permits(Role.DISPATCHER))):
    return handover.issue(plan_id, data, user['sub'])


@router.post('/plans/{plan_id}/handover/{brief_id}/arrival')
def arrival(plan_id: int, brief_id: int, data: ArrivalReport, user=Depends(permits(Role.INTAKE))):
    return handover.arrival(plan_id, brief_id, data, user['sub'])
