"""API v2 para workspace isolado no contêiner pessoal via broker."""

from __future__ import annotations

from pathlib import PurePosixPath

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from apps.AetherDesk.identity import ActorContext, IdentityService
from apps.AetherDesk.identity.service import IdentityError
from apps.AetherDesk.runtime.broker_ipc import BrokerClient, BrokerError
from apps.AetherDesk.support.http import require_mutation


class FileWrite(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    content: str = Field(max_length=2 * 1024 * 1024)


class Paths(BaseModel):
    paths: list[str] = Field(min_length=1, max_length=100)


class Commit(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    operationId: str


def workspace_router(broker: BrokerClient, identity: IdentityService,
                     csrf_secret: str) -> APIRouter:
    router = APIRouter(prefix='/api/v2/workspace')

    def actor(aether_session: str | None = Cookie(default=None)) -> ActorContext:
        if not aether_session:
            raise HTTPException(401, 'UNAUTHENTICATED')
        try:
            current = identity.actor(aether_session)
            identity.require(current, 'ide.open')
            return current
        except IdentityError as exc:
            raise HTTPException(403 if exc.code == 'FORBIDDEN' else 401, exc.code) from exc

    def mutation(request: Request, current: ActorContext,
                 aether_csrf: str | None, x_csrf_token: str | None):
        require_mutation(request, current.session_id, csrf_secret, aether_csrf, x_csrf_token)

    def call(current: ActorContext, operation: str, **kwargs):
        try:
            account = identity.account(current, current.account_id)
            return broker.call('workspace', current.account_id, account['environment_id'],
                               {'operation': operation, 'session_id': current.session_id, **kwargs})
        except IdentityError as exc:
            raise HTTPException(401 if exc.code == 'UNAUTHENTICATED' else 403, exc.code) from exc
        except BrokerError as exc:
            code = str(exc)
            status = (404 if code in ('NOT_FILE', 'NOT_FOUND') else
                      412 if code == 'STALE_REVISION' else
                      409 if code == 'OPERATION_CONFLICT' else
                      403 if code in ('FORBIDDEN', 'SESSION_REVOKED', 'ACCOUNT_INACTIVE') else
                      503 if code in ('BROKER_UNAVAILABLE', 'FILE_UNAVAILABLE', 'BROKER_BUSY',
                                      'UNKNOWN_WRITE_OUTCOME', 'WORKSPACE_AGENT_UPGRADE_REQUIRED',
                                      'FEATURE_DISABLED') else 422)
            raise HTTPException(status, code) from exc

    def envelope(data):
        return {'data': data}

    def language(path: str):
        suffix = PurePosixPath(path).suffix.lower()
        return {'.ts': 'typescript', '.tsx': 'typescript', '.js': 'javascript',
                '.jsx': 'javascript', '.py': 'python', '.json': 'json',
                '.css': 'css', '.html': 'html', '.md': 'markdown',
                '.sh': 'shell'}.get(suffix, 'plaintext')

    @router.get('/tree')
    def tree(current: ActorContext = Depends(actor)):
        return envelope(call(current, 'tree'))

    @router.get('/file')
    def read(path: str, current: ActorContext = Depends(actor)):
        result = call(current, 'read', path=path)
        if result['mode'] != 'text':
            return envelope({'path': path, 'content': '', 'revision': result.get('revision', ''),
                             'language': 'plaintext', 'readonly': True,
                             'reason': result['reason']})
        return envelope({'path': path, 'content': result['text'], 'revision': result['revision'],
                         'language': language(path), 'readonly': False})

    @router.put('/file')
    def write(payload: FileWrite, request: Request,
              current: ActorContext = Depends(actor),
              if_match: str | None = Header(default=None, alias='If-Match'),
              aether_csrf: str | None = Cookie(default=None),
              x_csrf_token: str | None = Header(default=None)):
        mutation(request, current, aether_csrf, x_csrf_token)
        if not if_match:
            raise HTTPException(428, 'REVISION_REQUIRED')
        result = call(current, 'write', path=payload.path, content=payload.content,
                      revision=if_match)
        return envelope({'path': payload.path, 'content': payload.content,
                         'revision': result['revision'], 'language': language(payload.path)})

    @router.get('/search')
    def search(q: str, current: ActorContext = Depends(actor)):
        result = call(current, 'search', query=q)
        return envelope([{'path': item['path'], 'line': item['line'],
                          'snippet': item['preview']} for item in result['matches']])

    @router.get('/git/status')
    def git_status(current: ActorContext = Depends(actor)):
        result = call(current, 'git_status')
        return envelope({'branch': result['branch'], 'ahead': 0, 'behind': 0,
                         'entries': [{'path': item['path'], 'status': item['code'],
                                      'staged': item['code'][0] != ' '}
                                     for item in result['entries']]})

    @router.get('/git/diff')
    def git_diff(path: str, current: ActorContext = Depends(actor)):
        return envelope(call(current, 'git_diff', path=path)['text'])

    @router.post('/git/stage')
    def git_stage(payload: Paths, request: Request,
                  current: ActorContext = Depends(actor),
                  aether_csrf: str | None = Cookie(default=None),
                  x_csrf_token: str | None = Header(default=None)):
        mutation(request, current, aether_csrf, x_csrf_token)
        return envelope(call(current, 'git_stage', paths=payload.paths))

    @router.post('/git/commit')
    def git_commit(payload: Commit, request: Request,
                   current: ActorContext = Depends(actor),
                   aether_csrf: str | None = Cookie(default=None),
                   x_csrf_token: str | None = Header(default=None)):
        mutation(request, current, aether_csrf, x_csrf_token)
        result = call(current, 'git_commit', message=payload.message,
                      operation_id=payload.operationId)
        return envelope({'id': payload.operationId, 'status': 'completed',
                         'message': result['hash']})

    @router.post('/git/push')
    def git_push(request: Request, current: ActorContext = Depends(actor),
                 aether_csrf: str | None = Cookie(default=None),
                 x_csrf_token: str | None = Header(default=None)):
        mutation(request, current, aether_csrf, x_csrf_token)
        raise HTTPException(403, 'GIT_REMOTE_DISABLED')

    return router
