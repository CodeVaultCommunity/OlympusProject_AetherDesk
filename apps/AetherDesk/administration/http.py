"""Boundary de administração e estado do desktop."""

import hashlib
import hmac
import secrets
from typing import Literal

from fastapi import APIRouter, Cookie, Header, HTTPException, Request
from pydantic import BaseModel, Field

from apps.AetherDesk.identity import IdentityError, IdentityService
from .service import AdministrationError, AdministrationService


class BackupPolicy(BaseModel):
    enabled: bool = False
    frequency_hours: int = Field(default=24, ge=1, le=8760)
    destination: str = ''
    retention_mode: Literal['replace', 'days'] = 'replace'
    retention_days: int | None = Field(default=None, ge=1, le=3650)


def administration_router(service: AdministrationService, identity: IdentityService,
                          csrf_secret: str):
    router = APIRouter(prefix='/api/v1')

    def actor(token):
        try:
            return identity.actor(token or '')
        except IdentityError as exc:
            raise HTTPException(401, exc.code) from exc

    def mutation(request, current, csrf_cookie, csrf_header):
        origin = request.headers.get('origin')
        if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
            raise HTTPException(403, 'INVALID_ORIGIN')
        expected = hmac.new(csrf_secret.encode(), current.session_id.encode(), hashlib.sha256).hexdigest()
        if not csrf_cookie or not csrf_header or not secrets.compare_digest(csrf_cookie, expected) or not secrets.compare_digest(csrf_header, expected):
            raise HTTPException(403, 'INVALID_CSRF')

    def call(operation):
        try:
            return {'data': operation()}
        except IdentityError as exc:
            raise HTTPException(403, exc.code) from exc
        except AdministrationError as exc:
            raise HTTPException(422, exc.code) from exc

    @router.get('/desktop/state')
    def desktop(aether_session: str | None = Cookie(default=None)):
        current = actor(aether_session)
        return call(lambda: service.get_desktop(current))

    @router.put('/desktop/state')
    def save_desktop(body: dict, request: Request, aether_session: str | None = Cookie(default=None),
                     aether_csrf: str | None = Cookie(default=None), x_csrf_token: str | None = Header(default=None)):
        current = actor(aether_session)
        mutation(request, current, aether_csrf, x_csrf_token)
        return call(lambda: service.put_desktop(current, body))

    @router.get('/admin/accounts')
    def accounts(aether_session: str | None = Cookie(default=None)):
        current = actor(aether_session)
        return call(lambda: service.accounts(current))

    @router.get('/admin/accounts/{account_id}/permissions')
    def permissions(account_id: str, aether_session: str | None = Cookie(default=None)):
        current = actor(aether_session)
        return call(lambda: service.permissions(current, account_id))

    @router.get('/admin/accounts/{account_id}/sessions')
    def sessions(account_id: str, aether_session: str | None = Cookie(default=None)):
        current = actor(aether_session)
        return call(lambda: service.sessions(current, account_id))

    @router.get('/admin/accounts/{account_id}/environment')
    def environment(account_id: str, aether_session: str | None = Cookie(default=None)):
        current = actor(aether_session)
        return call(lambda: service.environment(current, account_id))

    @router.post('/admin/accounts/{account_id}/environment/retry')
    def retry(account_id: str, request: Request, aether_session: str | None = Cookie(default=None),
              aether_csrf: str | None = Cookie(default=None), x_csrf_token: str | None = Header(default=None)):
        current = actor(aether_session)
        mutation(request, current, aether_csrf, x_csrf_token)
        return call(lambda: service.retry_environment(current, account_id))

    @router.post('/admin/accounts/{account_id}/sessions/stop')
    def stop(account_id: str, request: Request, aether_session: str | None = Cookie(default=None),
             aether_csrf: str | None = Cookie(default=None), x_csrf_token: str | None = Header(default=None)):
        current = actor(aether_session)
        mutation(request, current, aether_csrf, x_csrf_token)
        return call(lambda: service.stop_session(current, account_id))

    @router.get('/admin/audit')
    def audit(aether_session: str | None = Cookie(default=None)):
        current = actor(aether_session)
        return call(lambda: service.audit(current))

    @router.get('/admin/backup')
    def backup(aether_session: str | None = Cookie(default=None)):
        current = actor(aether_session)
        return call(lambda: service.backup_settings(current))

    @router.put('/admin/backup')
    def configure_backup(policy: BackupPolicy, request: Request,
                         aether_session: str | None = Cookie(default=None),
                         aether_csrf: str | None = Cookie(default=None), x_csrf_token: str | None = Header(default=None)):
        current = actor(aether_session)
        mutation(request, current, aether_csrf, x_csrf_token)
        return call(lambda: service.configure_backup(current, **policy.model_dump()))

    return router
