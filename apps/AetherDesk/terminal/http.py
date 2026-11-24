"""Boundary HTTP/WS para PTY, com rechecagem de autorização em fluxo aberto."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Cookie, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from apps.AetherDesk.identity import IdentityError, IdentityService
from apps.AetherDesk.support.http import require_mutation
from apps.AetherDesk.runtime.broker_ipc import BrokerError
from .service import TerminalError, TerminalService


class TerminalSize(BaseModel):
    columns: int = Field(default=80, ge=20, le=400)
    rows: int = Field(default=24, ge=5, le=200)


def parse_terminal_control(raw: str) -> dict:
    if len(raw) > 4096:
        raise TerminalError('INVALID_CONTROL_MESSAGE')
    try:
        command = json.loads(raw)
    except ValueError as exc:
        raise TerminalError('INVALID_CONTROL_MESSAGE') from exc
    if not isinstance(command, dict):
        raise TerminalError('INVALID_CONTROL_MESSAGE')
    kind = command.get('type')
    valid = ((kind == 'resize' and set(command) == {'type', 'columns', 'rows'} and
              type(command['columns']) is int and type(command['rows']) is int and
              20 <= command['columns'] <= 400 and 5 <= command['rows'] <= 200) or
             (kind == 'signal' and command == {'type': 'signal', 'name': 'INT'}) or
             (kind == 'close' and command == {'type': 'close'}))
    if not valid:
        raise TerminalError('INVALID_CONTROL_MESSAGE')
    return command


def terminal_router(service: TerminalService, identity: IdentityService,
                    csrf_secret: str) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    def terminal_status(code: str, default: int) -> int:
        if code in ('BROKER_UNAVAILABLE', 'BROKER_BUSY', 'BROKER_PROTOCOL',
                    'RUNTIME_UNAVAILABLE', 'TERMINAL_RECOVERING'):
            return 503
        return default

    def actor(token: str | None):
        if not token:
            raise HTTPException(401, "UNAUTHENTICATED")
        try:
            return identity.actor(token)
        except IdentityError as exc:
            raise HTTPException(401, exc.code) from exc

    def mutation(request: Request, current, cookie: str | None, header: str | None):
        require_mutation(request, current.session_id, csrf_secret, cookie, header)

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
            status = 403 if isinstance(exc, IdentityError) else terminal_status(exc.code, 409)
            raise HTTPException(status, exc.code) from exc

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
            status = 403 if isinstance(exc, IdentityError) else terminal_status(exc.code, 404)
            raise HTTPException(status, exc.code) from exc

    @router.websocket("/ws/terminals/{terminal_id}")
    async def terminal_socket(ws: WebSocket, terminal_id: str):
        origin = ws.headers.get("origin")
        expected_origin = f"{ws.url.scheme.replace('ws', 'http')}://{ws.url.netloc}"
        if not origin or origin.rstrip("/") != expected_origin:
            await ws.close(code=4403)
            return
        try:
            current = identity.actor(ws.cookies.get("aether_session", ""))
            connection = service.attach(current, terminal_id)
        except (IdentityError, TerminalError, BrokerError) as exc:
            await ws.close(code=1013 if isinstance(exc, BrokerError) else 4403)
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
                    if len(message['bytes']) > 65536:
                        raise TerminalError('INVALID_CONTROL_MESSAGE')
                    connection.write(message["bytes"])
                    continue
                if message.get("text"):
                    command = parse_terminal_control(message["text"])
                    if command['type'] == "resize":
                        connection.resize(command["columns"], command["rows"])
                    elif command['type'] == "signal":
                        connection.write(b"\x03")
                    elif command['type'] == "close":
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
        except TerminalError as exc:
            await ws.close(code=4400 if exc.code == 'INVALID_CONTROL_MESSAGE' else 4403)
        except IdentityError:
            await ws.close(code=4403)
        except (WebSocketDisconnect, OSError):
            pass
        finally:
            connection.close()
            for task in tasks:
                task.cancel()

    return router
