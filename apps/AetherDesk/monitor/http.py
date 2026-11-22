"""Boundary de métricas: toda visão exige capacidade própria."""

from fastapi import APIRouter, Cookie, HTTPException

from apps.AetherDesk.identity import IdentityError, IdentityService
from .service import MonitorService


def monitor_router(service: MonitorService, identity: IdentityService, list_accounts):
    router = APIRouter(prefix='/api/v1/metrics')

    def current(token):
        try:
            return identity.actor(token or '')
        except IdentityError as exc:
            raise HTTPException(401, exc.code) from exc

    @router.get('/self')
    def self_metrics(aether_session: str | None = Cookie(default=None)):
        try:
            return {'data': service.self(current(aether_session))}
        except IdentityError as exc:
            raise HTTPException(403, exc.code) from exc

    @router.get('/server')
    def server_metrics(aether_session: str | None = Cookie(default=None)):
        try:
            actor = current(aether_session)
            try:
                accounts = list_accounts(actor)
            except IdentityError:
                accounts = None
            return {'data': service.server(actor, accounts)}
        except IdentityError as exc:
            raise HTTPException(403, exc.code) from exc

    @router.get('/accounts')
    def account_metrics(aether_session: str | None = Cookie(default=None)):
        try:
            actor = current(aether_session)
            return {'data': service.accounts(actor, list_accounts(actor))}
        except IdentityError as exc:
            raise HTTPException(403, exc.code) from exc

    return router
