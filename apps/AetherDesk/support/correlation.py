"""Identificador de requisição propagado do HTTP para o IPC do broker."""

from contextvars import ContextVar


request_id_context: ContextVar[str | None] = ContextVar('aetherdesk_request_id', default=None)
