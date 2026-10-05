from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.core.clock import SystemClock
from app.core.config import ApiSettings
from app.core.db import create_database_engine, create_session_factory
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import TrustedProxyMiddleware, request_context_middleware
from app.health import router as health_router
from app.modules.business.router import router as business_router
from app.modules.clients.router import router as clients_router
from app.modules.identity.router import router as identity_router


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    resolved = settings or ApiSettings()
    logger = configure_logging(resolved.LOG_LEVEL)
    engine = create_database_engine(resolved)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    app = FastAPI(
        title="ClientOps API",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = resolved
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.logger = logger
    app.state.clock = SystemClock()
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(resolved.trusted_hosts))
    app.add_middleware(TrustedProxyMiddleware, settings=resolved)
    app.middleware("http")(request_context_middleware)
    install_error_handlers(app)
    app.include_router(health_router)
    app.include_router(identity_router)
    app.include_router(business_router)
    app.include_router(clients_router)
    return app
