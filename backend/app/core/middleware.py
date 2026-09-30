from __future__ import annotations

import ipaddress
import time
from collections.abc import Awaitable, Callable
from typing import ClassVar
from uuid import UUID, uuid4

from fastapi import Request, Response
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import ApiSettings


class TrustedProxyMiddleware:
    forwarded_headers: ClassVar[set[bytes]] = {
        b"x-forwarded-for",
        b"x-forwarded-host",
        b"x-forwarded-proto",
    }

    def __init__(self, app: ASGIApp, settings: ApiSettings) -> None:
        self.app = app
        self.networks = settings.trusted_proxy_networks

    def _trusted(self, host: str) -> bool:
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return False
        return any(address in network for network in self.networks)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            client = scope.get("client")
            trusted = bool(client and self._trusted(client[0]))
            if not trusted:
                scope = dict(scope)
                scope["headers"] = [
                    (name, value)
                    for name, value in scope.get("headers", [])
                    if name.lower() not in self.forwarded_headers
                ]
            else:
                headers = Headers(scope=scope)
                proto = headers.get("x-forwarded-proto")
                if proto in {"http", "https"}:
                    scope = dict(scope)
                    scope["scheme"] = proto
        await self.app(scope, receive, send)


def _validated_request_id(raw: str | None) -> UUID:
    if raw is not None:
        try:
            return UUID(raw)
        except ValueError:
            pass
    return uuid4()


async def request_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = _validated_request_id(request.headers.get("X-Request-ID"))
    request.state.request_id = request_id
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = str(request_id)
    route = request.scope.get("route")
    template = getattr(route, "path", "<unmatched>")
    request.app.state.logger.info(
        "request_completed",
        extra={
            "request_id": str(request_id),
            "method": request.method,
            "route": template,
            "status": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        },
    )
    return response
