"""Boundary HTTP de arquivos sem parâmetros de dono ou ambiente."""

import hashlib
import hmac
import secrets

from fastapi import APIRouter, Cookie, Header, HTTPException, Request, Response
from pydantic import BaseModel

from apps.AetherDesk.identity import IdentityError, IdentityService
from .gateway import ContainerFileGateway
from .service import FileError


class PathBody(BaseModel):
    path: str


class PairBody(PathBody):
    destination: str


class ContentBody(PathBody):
    content: str


def files_router(gateway: ContainerFileGateway, identity: IdentityService, csrf_secret: str):
    router = APIRouter(prefix='/api/v1/files')

    def actor(token):
        try:
            return identity.actor(token or '')
        except IdentityError as exc:
            raise HTTPException(401, exc.code) from exc

    def mutation(request, current, cookie, header):
        origin = request.headers.get('origin')
        if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
            raise HTTPException(403, 'INVALID_ORIGIN')
        expected = hmac.new(csrf_secret.encode(), current.session_id.encode(), hashlib.sha256).hexdigest()
        if not cookie or not header or not secrets.compare_digest(cookie, expected) or not secrets.compare_digest(header, expected):
            raise HTTPException(403, 'INVALID_CSRF')

    def call(function):
        try:
            return function()
        except IdentityError as exc:
            raise HTTPException(403, exc.code) from exc
        except FileError as exc:
            status = {'NOT_FOUND': 404, 'CONFLICT': 409, 'STALE_REVISION': 412,
                      'FORBIDDEN': 403, 'TOO_LARGE': 413, 'QUOTA': 507}.get(exc.code, 422)
            raise HTTPException(status, exc.code) from exc

    @router.get('/list')
    def list_files(path: str = '/', aether_session: str | None = Cookie(default=None)):
        current = actor(aether_session)
        return {'data': call(lambda: gateway.call(current, 'list', path))}

    @router.get('/metadata')
    def metadata(path: str, aether_session: str | None = Cookie(default=None)):
        current = actor(aether_session)
        return {'data': call(lambda: gateway.call(current, 'metadata', path))}

    @router.get('/content')
    def read(path: str, aether_session: str | None = Cookie(default=None)):
        current = actor(aether_session)
        data, revision = call(lambda: gateway.read(current, path))
        try:
            content = data.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise HTTPException(415, 'NOT_TEXT') from exc
        return {'data': {'content': content, 'revision': revision}}

    @router.get('/download')
    def download(path: str, aether_session: str | None = Cookie(default=None)):
        current = actor(aether_session)
        data, _ = call(lambda: gateway.read(current, path))
        return Response(data, media_type='application/octet-stream',
                        headers={'Content-Disposition': 'attachment'})

    @router.put('/content')
    def write(body: ContentBody, request: Request, revision: str | None = Header(default=None, alias='If-Match'),
              replace: bool = False, aether_session: str | None = Cookie(default=None),
              aether_csrf: str | None = Cookie(default=None), x_csrf_token: str | None = Header(default=None)):
        current = actor(aether_session)
        mutation(request, current, aether_csrf, x_csrf_token)
        return {'data': {'revision': call(lambda: gateway.write(current, body.path, body.content.encode(), revision, replace))}}

    @router.post('/mkdir')
    def mkdir(body: PathBody, request: Request, aether_session: str | None = Cookie(default=None),
              aether_csrf: str | None = Cookie(default=None), x_csrf_token: str | None = Header(default=None)):
        current = actor(aether_session); mutation(request, current, aether_csrf, x_csrf_token)
        return {'data': call(lambda: gateway.call(current, 'mkdir', body.path))}

    @router.post('/move')
    def move(body: PairBody, request: Request, aether_session: str | None = Cookie(default=None),
             aether_csrf: str | None = Cookie(default=None), x_csrf_token: str | None = Header(default=None)):
        current = actor(aether_session); mutation(request, current, aether_csrf, x_csrf_token)
        return {'data': call(lambda: gateway.call(current, 'move', body.path, destination=body.destination))}

    @router.post('/copy')
    def copy(body: PairBody, request: Request, aether_session: str | None = Cookie(default=None),
             aether_csrf: str | None = Cookie(default=None), x_csrf_token: str | None = Header(default=None)):
        current = actor(aether_session); mutation(request, current, aether_csrf, x_csrf_token)
        return {'data': call(lambda: gateway.call(current, 'copy', body.path, destination=body.destination))}

    @router.delete('/entry')
    def delete(body: PathBody, request: Request, aether_session: str | None = Cookie(default=None),
               aether_csrf: str | None = Cookie(default=None), x_csrf_token: str | None = Header(default=None)):
        current = actor(aether_session); mutation(request, current, aether_csrf, x_csrf_token)
        return {'data': call(lambda: gateway.call(current, 'delete', body.path))}

    @router.put('/upload')
    async def upload(request: Request, path: str, replace: bool = False,
                     aether_session: str | None = Cookie(default=None),
                     aether_csrf: str | None = Cookie(default=None), x_csrf_token: str | None = Header(default=None)):
        current = actor(aether_session); mutation(request, current, aether_csrf, x_csrf_token)
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > 8 * 1024 * 1024:
                raise HTTPException(413, 'TOO_LARGE')
        return {'data': {'revision': call(lambda: gateway.write(current, path, bytes(content), replace=replace))}}

    return router
