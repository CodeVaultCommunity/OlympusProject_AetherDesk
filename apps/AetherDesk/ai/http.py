"""API v2 de chat local com provider explícito e conteúdo não interpretado como tool."""

from __future__ import annotations

import json
import threading
from contextlib import closing

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from apps.AetherDesk.identity import ActorContext, IdentityService
from apps.AetherDesk.identity.service import IdentityError
from apps.AetherDesk.runtime.broker_ipc import BrokerError
from apps.AetherDesk.support.http import require_mutation
from apps.AetherDesk.support.migrations import apply_migration

from .approval import AiError
from .chat import ChatService
from .tools import NativeTools


class NewConversation(BaseModel):
    provider: str = Field(min_length=1, max_length=64)


class ProviderSetting(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=64)
    secret: str | None = Field(default=None, max_length=65536)


class StreamPrompt(BaseModel):
    prompt: str = Field(min_length=1, max_length=16384)
    disclosureAccepted: bool = False


class ApprovalRequest(BaseModel):
    proposalId: str


class ApprovalGrant(BaseModel):
    nonce: str


class ToolInvocation(BaseModel):
    proposalId: str
    ticketId: str
    nonce: str
    operationId: str


def ai_router(service: ChatService, identity: IdentityService, csrf_secret: str,
              tools: NativeTools | None = None) -> APIRouter:
    router = APIRouter(prefix='/api/v2/ai')
    apply_migration(service.db_path, 'ai.provider_settings.v1', lambda db: db.execute('''
        CREATE TABLE IF NOT EXISTS ai_provider_settings (
            owner_id TEXT PRIMARY KEY, provider TEXT NOT NULL, model TEXT NOT NULL)'''))

    def actor(aether_session: str | None = Cookie(default=None)) -> ActorContext:
        if not aether_session:
            raise HTTPException(401, 'UNAUTHENTICATED')
        try:
            current = identity.actor(aether_session)
            identity.require(current, 'ai.chat')
            return current
        except IdentityError as exc:
            raise HTTPException(403 if exc.code == 'FORBIDDEN' else 401, exc.code) from exc

    def mutation(request: Request, current: ActorContext,
                 aether_csrf: str | None, x_csrf_token: str | None):
        require_mutation(request, current.session_id, csrf_secret, aether_csrf, x_csrf_token)

    def envelope(data):
        return {'data': data}

    def mapped(error: AiError):
        code = str(error)
        status = 404 if code in ('CONVERSATION_NOT_FOUND', 'PROPOSAL_NOT_FOUND') else (
            403 if code in ('SESSION_REVOKED', 'PROVIDER_DISABLED', 'DISCLOSURE_REQUIRED') else
            409 if code in ('APPROVAL_MISMATCH', 'APPROVAL_REPLAY', 'APPROVAL_EXPIRED',
                           'OPERATION_CONFLICT', 'OPERATION_ALREADY_USED') else
            429 if code in ('RATE_LIMITED', 'QUOTA_EXCEEDED') else
            503 if code == 'TOOL_FAILED' else 422)
        raise HTTPException(status, code) from error

    def tool_call(current: ActorContext, method: str, *args):
        try:
            identity.require(current, 'ai.tools')
            if tools is None:
                if method == 'proposals':
                    return []
                raise HTTPException(503, 'TOOLS_DISABLED')
            identity.require(current, 'workloads.control')
            return getattr(tools, method)(current, *args)
        except IdentityError as exc:
            raise HTTPException(403, exc.code) from exc
        except BrokerError as exc:
            raise HTTPException(503, str(exc)) from exc
        except AiError as exc:
            mapped(exc)

    @router.get('/providers')
    def providers(current: ActorContext = Depends(actor)):
        result = []
        for name, provider in service.providers.items():
            result.append({'name': name, 'models': ['demo'] if name == 'local-demo' else [],
                           'external': provider.external, 'enabled': name in service.enabled_providers,
                           'dataSent': provider.disclosure, 'retentionDays': service.retention_days,
                           'costPerThousand': str(provider.cost_micros_per_1000_chars)})
        return envelope(result)

    @router.post('/provider')
    def save_provider(payload: ProviderSetting, request: Request,
                      current: ActorContext = Depends(actor),
                      aether_csrf: str | None = Cookie(default=None),
                      x_csrf_token: str | None = Header(default=None)):
        mutation(request, current, aether_csrf, x_csrf_token)
        if payload.name not in service.enabled_providers or payload.name != 'local-demo' or payload.model != 'demo':
            raise HTTPException(403, 'PROVIDER_DISABLED')
        if payload.secret:
            raise HTTPException(422, 'CREDENTIALS_NOT_SUPPORTED')
        with closing(service._db()) as db, db:
            db.execute('''INSERT INTO ai_provider_settings(owner_id,provider,model) VALUES(?,?,?)
                ON CONFLICT(owner_id) DO UPDATE SET provider=excluded.provider,model=excluded.model''',
                (current.account_id, payload.name, payload.model))
        return envelope({'saved': True})

    @router.get('/conversations')
    def conversations(current: ActorContext = Depends(actor)):
        try:
            return envelope([{'id': item['id'], 'provider': item['provider'],
                              'title': f"Conversa {item['id'][:8]}", 'updatedAt': item['updated_at']}
                             for item in service.conversations(current)])
        except AiError as exc:
            mapped(exc)

    @router.post('/conversations')
    def create(payload: NewConversation, request: Request,
               current: ActorContext = Depends(actor),
               aether_csrf: str | None = Cookie(default=None),
               x_csrf_token: str | None = Header(default=None)):
        mutation(request, current, aether_csrf, x_csrf_token)
        try:
            conversation_id = service.create(current, payload.provider)
        except AiError as exc:
            mapped(exc)
        return envelope({'id': conversation_id, 'provider': payload.provider,
                         'title': f'Conversa {conversation_id[:8]}', 'updatedAt': service.clock()})

    @router.get('/conversations/{conversation_id}/messages')
    def messages(conversation_id: str, current: ActorContext = Depends(actor)):
        try:
            return envelope(service.messages(current, conversation_id))
        except AiError as exc:
            mapped(exc)

    @router.get('/conversations/{conversation_id}/export')
    def export(conversation_id: str, current: ActorContext = Depends(actor)):
        try:
            return envelope(service.export(current, conversation_id))
        except AiError as exc:
            mapped(exc)

    @router.delete('/conversations/{conversation_id}')
    def delete(conversation_id: str, request: Request,
               current: ActorContext = Depends(actor),
               aether_csrf: str | None = Cookie(default=None),
               x_csrf_token: str | None = Header(default=None)):
        mutation(request, current, aether_csrf, x_csrf_token)
        try:
            service.delete(current, conversation_id)
        except AiError as exc:
            mapped(exc)
        return envelope({'deleted': True})

    @router.get('/usage')
    def usage(current: ActorContext = Depends(actor)):
        try:
            result = service.usage(current)
        except AiError as exc:
            mapped(exc)
        return envelope({'usedChars': result['used_chars'], 'limitChars': result['limit_chars'],
                         'cost': str(result['used_cost_micros']),
                         'limitCost': str(result['limit_cost_micros'])})

    @router.post('/conversations/{conversation_id}/stream')
    def stream(conversation_id: str, payload: StreamPrompt, request: Request,
               current: ActorContext = Depends(actor),
               aether_csrf: str | None = Cookie(default=None),
               x_csrf_token: str | None = Header(default=None)):
        mutation(request, current, aether_csrf, x_csrf_token)
        cancel = threading.Event()
        def chunks():
            try:
                for chunk in service.stream(current, conversation_id, payload.prompt,
                                            disclosure_accepted=payload.disclosureAccepted,
                                            cancel=cancel):
                    yield json.dumps({'type': 'chunk', 'text': chunk}, ensure_ascii=False) + '\n'
            except AiError as exc:
                yield json.dumps({'type': 'error', 'code': str(exc)}) + '\n'
            finally:
                cancel.set()
        return StreamingResponse(chunks(), media_type='application/x-ndjson',
                                 headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})

    @router.get('/tools/proposals')
    def proposals(current: ActorContext = Depends(actor)):
        return envelope(tool_call(current, 'proposals'))

    @router.post('/tools/approvals')
    def request_approval(payload: ApprovalRequest, request: Request,
                         current: ActorContext = Depends(actor),
                         aether_csrf: str | None = Cookie(default=None),
                         x_csrf_token: str | None = Header(default=None)):
        mutation(request, current, aether_csrf, x_csrf_token)
        ticket = tool_call(current, 'request', payload.proposalId)
        return envelope({'id': ticket['id'], 'tool': ticket['tool'], 'version': ticket['version'],
                         'argumentsHash': ticket['arguments_hash'],
                         'expiresAt': ticket['expires_at'], 'nonce': ticket['nonce']})

    @router.post('/tools/approvals/{ticket_id}/approve')
    def approve(ticket_id: str, payload: ApprovalGrant, request: Request,
                current: ActorContext = Depends(actor),
                aether_csrf: str | None = Cookie(default=None),
                x_csrf_token: str | None = Header(default=None)):
        mutation(request, current, aether_csrf, x_csrf_token)
        tool_call(current, 'approve', ticket_id, payload.nonce)
        return envelope({'approved': True})

    @router.post('/tools/invoke')
    def invoke(payload: ToolInvocation, request: Request,
               current: ActorContext = Depends(actor),
               aether_csrf: str | None = Cookie(default=None),
               x_csrf_token: str | None = Header(default=None)):
        mutation(request, current, aether_csrf, x_csrf_token)
        return envelope(tool_call(current, 'invoke', payload.proposalId, payload.ticketId,
                                  payload.nonce, payload.operationId))

    return router
