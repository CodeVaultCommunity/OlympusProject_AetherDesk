"""API v2 de workloads: identidade por cookie e execução exclusivamente via broker."""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from apps.AetherDesk.identity import ActorContext, IdentityService
from apps.AetherDesk.identity.service import IdentityError
from apps.AetherDesk.runtime.broker_ipc import BrokerClient, BrokerError
from apps.AetherDesk.support.http import require_mutation
from .gateway import RouteGateway


class NewWorkload(BaseModel):
    project: str = Field(min_length=1, max_length=61)
    name: str = Field(min_length=1, max_length=51)


class Action(BaseModel):
    action: str
    operationId: str
    template: str | None = None


class SecretRefs(BaseModel):
    references: dict[str, str]
    operationId: str


def workloads_router(broker: BrokerClient, identity: IdentityService,
                     csrf_secret: str, gateway: RouteGateway | None = None) -> APIRouter:
    router = APIRouter(prefix='/api/v2')

    def actor(aether_session: str | None = Cookie(default=None)) -> ActorContext:
        if not aether_session:
            raise HTTPException(401, 'UNAUTHENTICATED')
        try:
            return identity.actor(aether_session)
        except IdentityError as exc:
            raise HTTPException(401, exc.code) from exc

    def mutation(request: Request, current: ActorContext,
                 aether_csrf: str | None, x_csrf_token: str | None):
        require_mutation(request, current.session_id, csrf_secret, aether_csrf, x_csrf_token)

    def call(current: ActorContext, operation: str, **kwargs):
        try:
            account = identity.account(current, current.account_id)
            return broker.call('workload', current.account_id, account['environment_id'],
                               {'operation': operation, 'session_id': current.session_id, **kwargs})
        except IdentityError as exc:
            raise HTTPException(401 if exc.code == 'UNAUTHENTICATED' else 403, exc.code) from exc
        except BrokerError as exc:
            code = str(exc)
            status = (404 if code in ('WORKLOAD_NOT_FOUND', 'JOB_NOT_FOUND', 'PROJECT_NOT_FOUND') else
                      403 if code in ('FORBIDDEN', 'OPERATION_DENIED', 'SESSION_REVOKED',
                                      'ACCOUNT_INACTIVE', 'SECRETS_DISABLED') else
                      409 if code in ('OPERATION_CONFLICT', 'WORKLOAD_REMOVED', 'NO_DEPLOYMENT') else
                      503 if code in ('BROKER_UNAVAILABLE', 'RUNTIME_UNAVAILABLE', 'BROKER_BUSY',
                                      'UNKNOWN_WRITE_OUTCOME', 'FEATURE_DISABLED') else 422)
            raise HTTPException(status, code) from exc

    def envelope(data):
        return {'data': data}

    def job_shape(row: dict) -> dict:
        return {'id': row['id'], 'workloadId': row.get('workload_id', ''),
                'action': row.get('action', ''), 'status': row['status'],
                'errorCode': row.get('error_code')}

    @router.get('/workloads/mine')
    def mine(current: ActorContext = Depends(actor)):
        items = call(current, 'list_mine')['items']
        if gateway is not None and 'workloads.route' in identity.capabilities(current):
            for item in items:
                if item['observed'] in ('running', 'rolled_back') and item['port']:
                    item['route'] = gateway.host_for(item['id'])
        return envelope(items)

    @router.get('/workloads/controllable')
    def controllable(current: ActorContext = Depends(actor)):
        return envelope(call(current, 'list_controllable')['items'])

    @router.get('/workloads/templates')
    def templates(current: ActorContext = Depends(actor)):
        return envelope(call(current, 'templates')['items'])

    @router.post('/workloads')
    def create(payload: NewWorkload, request: Request,
               current: ActorContext = Depends(actor),
               aether_csrf: str | None = Cookie(default=None),
               x_csrf_token: str | None = Header(default=None)):
        mutation(request, current, aether_csrf, x_csrf_token)
        project = call(current, 'project', name=payload.project)
        return envelope(call(current, 'create', project_id=project['id'], name=payload.name))

    @router.post('/workloads/build')
    def build(request: Request, current: ActorContext = Depends(actor),
              aether_csrf: str | None = Cookie(default=None),
              x_csrf_token: str | None = Header(default=None)):
        mutation(request, current, aether_csrf, x_csrf_token)
        if 'workloads.build' not in identity.capabilities(current):
            raise HTTPException(403, 'FORBIDDEN')
        raise HTTPException(503, 'BUILD_SCANNER_NOT_CONFIGURED')

    @router.post('/workloads/{workload_id}/actions')
    def action(workload_id: str, payload: Action, request: Request,
               current: ActorContext = Depends(actor),
               aether_csrf: str | None = Cookie(default=None),
               x_csrf_token: str | None = Header(default=None)):
        mutation(request, current, aether_csrf, x_csrf_token)
        if payload.action not in ('deploy', 'start', 'stop', 'restart', 'remove'):
            raise HTTPException(422, 'INVALID_ACTION')
        try:
            row = call(current, 'request', workload_id=workload_id, action=payload.action,
                       operation_id=payload.operationId, template=payload.template)
        except HTTPException as exc:
            if exc.status_code != 404 or payload.action not in ('stop', 'restart', 'remove'):
                raise
            row = call(current, 'admin_request', workload_id=workload_id,
                       action=payload.action, operation_id=payload.operationId)
        return envelope({'id': row['id'], 'workloadId': workload_id,
                         'action': payload.action, 'status': row['status']})

    @router.get('/jobs/{job_id}')
    def job(job_id: str, current: ActorContext = Depends(actor)):
        return envelope(job_shape(call(current, 'job', job_id=job_id)))

    @router.post('/jobs/{job_id}/cancel')
    def cancel(job_id: str, request: Request, current: ActorContext = Depends(actor),
               aether_csrf: str | None = Cookie(default=None),
               x_csrf_token: str | None = Header(default=None)):
        mutation(request, current, aether_csrf, x_csrf_token)
        return envelope(job_shape(call(current, 'cancel', job_id=job_id)))

    @router.get('/workloads/{workload_id}/logs')
    def logs(workload_id: str, current: ActorContext = Depends(actor)):
        return envelope(call(current, 'logs', workload_id=workload_id)['text'])

    @router.get('/workloads/{workload_id}/metrics')
    def metrics(workload_id: str, current: ActorContext = Depends(actor)):
        return envelope(call(current, 'metrics', workload_id=workload_id))

    @router.post('/workloads/{workload_id}/route-ticket')
    def route_ticket(workload_id: str, request: Request,
                     current: ActorContext = Depends(actor),
                     aether_csrf: str | None = Cookie(default=None),
                     x_csrf_token: str | None = Header(default=None)):
        mutation(request, current, aether_csrf, x_csrf_token)
        if gateway is None:
            raise HTTPException(503, 'ROUTE_DISABLED')
        try:
            return envelope(gateway.issue(current, workload_id))
        except IdentityError as exc:
            raise HTTPException(403, exc.code) from exc
        except ValueError as exc:
            raise HTTPException(429 if str(exc) == 'ROUTE_RATE_LIMITED' else 422,
                                str(exc)) from exc
        except BrokerError as exc:
            raise HTTPException(503, str(exc)) from exc

    @router.post('/workloads/{workload_id}/secrets')
    def secrets(workload_id: str, payload: SecretRefs, request: Request,
                current: ActorContext = Depends(actor),
                aether_csrf: str | None = Cookie(default=None),
                x_csrf_token: str | None = Header(default=None)):
        mutation(request, current, aether_csrf, x_csrf_token)
        return envelope(call(current, 'configure_secrets', workload_id=workload_id,
                             references=payload.references, operation_id=payload.operationId))

    return router
