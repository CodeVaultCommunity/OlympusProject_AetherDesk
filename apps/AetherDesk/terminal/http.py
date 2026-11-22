"""Boundary HTTP/WS para PTY, com rechecagem de autorização em fluxo aberto."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets

from fastapi import APIRouter, Cookie, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from apps.AetherDesk.identity import IdentityError, IdentityService
from .service import TerminalError, TerminalService


class TerminalSize(BaseModel):
    columns: int = Field(default=80, ge=20, le=400)
    rows: int = Field(default=24, ge=5, le=200)


def terminal_router(service: TerminalService, identity: IdentityService,
                    csrf_secret: str) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    def actor(token: str | None):
        if not token:
            raise HTTPException(401, "UNAUTHENTICATED")
        try:
            return identity.actor(token)
        except IdentityError as exc:
            raise HTTPException(401, exc.code) from exc

    def mutation(request: Request, current, cookie: str | None, header: str | None):
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "INVALID_ORIGIN")
        expected = hmac.new(csrf_secret.encode(), current.session_id.encode(), hashlib.sha256).hexdigest()
        if not cookie or not header or not secrets.compare_digest(cookie, expected) or not secrets.compare_digest(header, expected):
            raise HTTPException(403, "INVALID_CSRF")

    @router.get("/terminals")
    def list_terminals(aether_session: str | None = Cookie(default=None)):
        current = actor(aether_session)
        try:
            return {"data": service.list(current)}
        except IdentityError as exc:
            raise HTTPException(403, exc.code) from exc

    @router.post("/terminals")
    def create_terminal(size: TerminalSize, request: Request,
                        aether_session: str | None = Cookie(default=None),
                        aether_csrf: str | None = Cookie(default=None),
                        x_csrf_token: str | None = Header(default=None)):
        current = actor(aether_session)
        mutation(request, current, aether_csrf, x_csrf_token)
        try:
            return {"data": {"id": service.create(current, size.columns, size.rows)}}
        except (IdentityError, TerminalError) as exc:
            raise HTTPException(403 if isinstance(exc, IdentityError) else 409, exc.code) from exc

    @router.delete("/terminals/{terminal_id}")
    def close_terminal(terminal_id: str, request: Request,
                       aether_session: str | None = Cookie(default=None),
                       aether_csrf: str | None = Cookie(default=None),
                       x_csrf_token: str | None = Header(default=None)):
        current = actor(aether_session)
        mutation(request, current, aether_csrf, x_csrf_token)
        try:
            service.close(current, terminal_id)
            return {"data": {"closed": True}}
        except (IdentityError, TerminalError) as exc:
            raise HTTPException(403 if isinstance(exc, IdentityError) else 404, exc.code) from exc

    @router.websocket("/ws/terminals/{terminal_id}")
    async def terminal_socket(ws: WebSocket, terminal_id: str):
        origin = ws.headers.get("origin")
        expected_origin = f"{ws.url.scheme.replace('ws', 'http')}://{ws.url.netloc}"
        if origin and origin.rstrip("/") != expected_origin:
            await ws.close(code=4403)
            return
        try:
            current = identity.actor(ws.cookies.get("aether_session", ""))
            connection = service.attach(current, terminal_id)
        except (IdentityError, TerminalError):
            await ws.close(code=4403)
            return
        await ws.accept()

        async def output():
            while True:
                data = await asyncio.to_thread(connection.read)
                if not data:
                    return
                await ws.send_bytes(data)

        async def input_messages():
            while True:
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    return
                if message.get("bytes") is not None:
                    connection.write(message["bytes"])
                    continue
                if message.get("text"):
                    command = json.loads(message["text"])
                    if command.get("type") == "resize":
                        connection.resize(int(command["columns"]), int(command["rows"]))
                    elif command.get("type") == "signal" and command.get("name") == "INT":
                        connection.write(b"\x03")
                    elif command.get("type") == "close":
                        service.close(current, terminal_id)
                        return

        async def guard():
            while True:
                await asyncio.sleep(0.25)
                identity.require(current, "terminal.control")

        tasks = [asyncio.create_task(task()) for task in (output, input_messages, guard)]
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task.exception():
                    raise task.exception()
            for task in pending:
                task.cancel()
        except (IdentityError, TerminalError):
            await ws.close(code=4403)
        except (WebSocketDisconnect, OSError):
            pass
        finally:
            connection.close()
            for task in tasks:
                task.cancel()

    return router
