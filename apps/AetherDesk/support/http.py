"""Política HTTP comum para Origin e CSRF das rotas autenticadas."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .correlation import request_id_context


def csrf_token(secret: str, session_id: str) -> str:
    return hmac.new(secret.encode(), session_id.encode(), hashlib.sha256).hexdigest()


def validate_origin(request: Request) -> None:
    origin = request.headers.get('origin')
    if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'INVALID_ORIGIN')


def require_mutation(request: Request, session_id: str, secret: str,
                     cookie: str | None, header: str | None) -> None:
    validate_origin(request)
    expected = csrf_token(secret, session_id)
    if not cookie or not header or not secrets.compare_digest(cookie, expected) or not secrets.compare_digest(header, expected):
        raise HTTPException(403, 'INVALID_CSRF')


def error_response(request: Request, status_code: int, detail,
                   headers: dict | None = None) -> JSONResponse:
    code = detail if isinstance(detail, str) and re.fullmatch(r'[A-Z][A-Z0-9_]{1,63}', detail) else 'HTTP_ERROR'
    return JSONResponse(status_code=status_code,
                        content={'detail': detail, 'error': {
                            'code': code, 'message': 'Não foi possível concluir a solicitação.',
                            'event_id': request.state.request_id,
                            'request_id': request.state.request_id,
                            'retryable': status_code in (429, 502, 503, 504) and
                                         code != 'UNKNOWN_WRITE_OUTCOME'}},
                        headers=headers)


def install_http_policy(app: FastAPI) -> None:
    """Preserva `detail` da API v1 e acrescenta erro estruturado e correlação."""

    @app.middleware('http')
    async def correlate(request: Request, call_next):
        request_id = secrets.token_hex(12)
        request.state.request_id = request_id
        token = request_id_context.set(request_id)
        try:
            requested_version = request.headers.get('X-AetherDesk-API-Version')
            if (request.url.path.startswith('/api/v2/') and requested_version is not None
                    and requested_version != '2'):
                response = error_response(request, 426, 'API_VERSION_UNSUPPORTED')
            else:
                response = await call_next(request)
        finally:
            request_id_context.reset(token)
        response.headers['X-Request-ID'] = request_id
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; "
            "form-action 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; font-src 'self' data:; "
            "connect-src 'self' ws: wss:; worker-src 'self' blob:")
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        if request.url.path.startswith('/api/v2/'):
            response.headers['X-AetherDesk-API-Version'] = '2'
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error_response(request, exc.status_code, exc.detail, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # A resposta v1 mantém `detail`; omite `input` para não refletir credenciais.
        detail = [{key: item[key] for key in ('type', 'loc', 'msg', 'url') if key in item}
                  for item in exc.errors()]
        return JSONResponse(status_code=422, content={'detail': detail, 'error': {
            'code': 'VALIDATION_ERROR', 'message': 'Dados inválidos.',
            'event_id': request.state.request_id,
            'request_id': request.state.request_id, 'retryable': False}})
