"""Boundary HTTP da identidade. Usa somente contexto autenticado do cookie."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Literal

from fastapi import APIRouter, Cookie, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .service import ActorContext, IdentityError, IdentityService


class Credentials(BaseModel):
    username: str
    password: str


class BootstrapCredentials(Credentials):
    token: str


class NewAccount(Credentials):
    role: Literal["admin", "member"] = "member"


class AccountUpdate(BaseModel):
    revision: int = Field(ge=1)
    username: str | None = None
    password: str | None = None
    state: Literal["active", "disabled", "deleted"] | None = None


class PermissionUpdate(BaseModel):
    capability: str
    allowed: bool


def _status(code: str) -> int:
    return {
        "UNAUTHENTICATED": 401, "FORBIDDEN": 403, "NOT_FOUND": 404,
        "CONFLICT": 409, "STALE_REVISION": 412, "LAST_ADMIN": 409,
    }.get(code, 422)


def identity_router(service: IdentityService, csrf_secret: str,
                    secure_cookie: bool = True) -> APIRouter:
    if len(csrf_secret) < 32:
        raise ValueError("CSRF secret must have at least 32 characters")
    router = APIRouter(prefix="/api/v1")

    def actor(session: str | None = Cookie(default=None, alias="aether_session")) -> ActorContext:
        if not session:
            raise HTTPException(401, "UNAUTHENTICATED")
        try:
            return service.actor(session)
        except IdentityError as exc:
            raise HTTPException(_status(exc.code), exc.code) from exc

    def csrf(request: Request, current: ActorContext,
             cookie: str | None, header: str | None) -> None:
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "INVALID_ORIGIN")
        expected = hmac.new(csrf_secret.encode(), current.session_id.encode(), hashlib.sha256).hexdigest()
        if not cookie or not header or not secrets.compare_digest(cookie, expected) or not secrets.compare_digest(header, expected):
            raise HTTPException(403, "INVALID_CSRF")

    def require_mutation(request: Request, current: ActorContext,
                         aether_csrf: str | None = Cookie(default=None),
                         x_csrf_token: str | None = Header(default=None)):
        csrf(request, current, aether_csrf, x_csrf_token)

    def result(data, revision: int | None = None):
        body = {"data": data, "event_id": secrets.token_hex(12)}
        if revision is not None:
            body["revision"] = revision
        return body

    @router.post("/bootstrap")
    def bootstrap(payload: BootstrapCredentials, request: Request):
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "INVALID_ORIGIN")
        try:
            return result({"account_id": service.bootstrap(payload.token, payload.username, payload.password)})
        except IdentityError as exc:
            raise HTTPException(_status(exc.code), exc.code) from exc

    @router.post("/login")
    def login(payload: Credentials, request: Request, response: Response):
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "INVALID_ORIGIN")
        try:
            token, current = service.login(payload.username, payload.password)
            profile = service.account(current, current.account_id)
        except IdentityError as exc:
            raise HTTPException(_status(exc.code), exc.code) from exc
        csrf_token = hmac.new(csrf_secret.encode(), current.session_id.encode(), hashlib.sha256).hexdigest()
        response.set_cookie("aether_session", token, httponly=True, secure=secure_cookie,
                            samesite="strict", path="/", max_age=43200)
        response.set_cookie("aether_csrf", csrf_token, httponly=False, secure=secure_cookie,
                            samesite="strict", path="/", max_age=43200)
        return result({"username": profile["username"], "role": profile["role"]})

    @router.get("/me")
    def me(session: str | None = Cookie(default=None, alias="aether_session")):
        current = actor(session)
        profile = service.account(current, current.account_id)
        return result({"username": profile["username"], "role": profile["role"],
                       "account_id": current.account_id, "permissions": sorted(service.capabilities(current))})

    @router.post("/logout")
    def logout(request: Request, response: Response,
               session: str | None = Cookie(default=None, alias="aether_session"),
               aether_csrf: str | None = Cookie(default=None),
               x_csrf_token: str | None = Header(default=None)):
        current = actor(session)
        require_mutation(request, current, aether_csrf, x_csrf_token)
        service.logout(session or "")
        response.delete_cookie("aether_session", path="/")
        response.delete_cookie("aether_csrf", path="/")
        return result({"logged_out": True})

    @router.post("/admin/accounts")
    def create_account(payload: NewAccount, request: Request,
                       session: str | None = Cookie(default=None, alias="aether_session"),
                       aether_csrf: str | None = Cookie(default=None),
                       x_csrf_token: str | None = Header(default=None)):
        current = actor(session)
        require_mutation(request, current, aether_csrf, x_csrf_token)
        try:
            account_id = service.create_account(current, payload.username, payload.password, payload.role)
            return result(service.account(current, account_id))
        except IdentityError as exc:
            raise HTTPException(_status(exc.code), exc.code) from exc

    @router.get("/admin/accounts/{account_id}")
    def get_account(account_id: str, session: str | None = Cookie(default=None, alias="aether_session")):
        current = actor(session)
        try:
            return result(service.account(current, account_id))
        except IdentityError as exc:
            raise HTTPException(_status(exc.code), exc.code) from exc

    @router.patch("/admin/accounts/{account_id}")
    def update_account(account_id: str, payload: AccountUpdate, request: Request,
                       session: str | None = Cookie(default=None, alias="aether_session"),
                       aether_csrf: str | None = Cookie(default=None),
                       x_csrf_token: str | None = Header(default=None)):
        current = actor(session)
        require_mutation(request, current, aether_csrf, x_csrf_token)
        try:
            value = service.update_account(current, account_id, username=payload.username,
                                           password=payload.password, state=payload.state,
                                           revision=payload.revision)
            return result(value, value["revision"])
        except IdentityError as exc:
            raise HTTPException(_status(exc.code), exc.code) from exc

    @router.put("/admin/accounts/{account_id}/permissions")
    def set_permission(account_id: str, payload: PermissionUpdate, request: Request,
                       session: str | None = Cookie(default=None, alias="aether_session"),
                       aether_csrf: str | None = Cookie(default=None),
                       x_csrf_token: str | None = Header(default=None)):
        current = actor(session)
        require_mutation(request, current, aether_csrf, x_csrf_token)
        try:
            service.set_permission(current, account_id, payload.capability, payload.allowed)
            return result({"account_id": account_id, "capability": payload.capability,
                           "allowed": payload.allowed})
        except IdentityError as exc:
            raise HTTPException(_status(exc.code), exc.code) from exc

    @router.post("/admin/sessions/{session_id}/revoke")
    def revoke_session(session_id: str, request: Request,
                       session: str | None = Cookie(default=None, alias="aether_session"),
                       aether_csrf: str | None = Cookie(default=None),
                       x_csrf_token: str | None = Header(default=None)):
        current = actor(session)
        require_mutation(request, current, aether_csrf, x_csrf_token)
        try:
            service.revoke_session(current, session_id)
            return result({"revoked": True})
        except IdentityError as exc:
            raise HTTPException(_status(exc.code), exc.code) from exc

    return router
