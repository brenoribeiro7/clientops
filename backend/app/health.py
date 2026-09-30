from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.errors import ErrorResponse, FoundationError
from app.storage.health import probe_private_storage


class HealthResponse(BaseModel):
    status: str


def expected_migration_heads() -> set[str]:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "migrations"))
    return set(ScriptDirectory.from_config(config).get_heads())


def check_database(engine: Engine) -> None:
    expected = expected_migration_heads()
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        actual = set(connection.execute(text("SELECT version_num FROM alembic_version")).scalars())
    if actual != expected:
        raise RuntimeError("migration_state_mismatch")


router = APIRouter(prefix="/api/v1/health", tags=["health"])


@router.get(
    "/live",
    response_model=HealthResponse,
    operation_id="healthLive",
    responses={500: {"model": ErrorResponse}},
)
def live(response: Response) -> HealthResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return HealthResponse(status="ok")


@router.get(
    "/ready",
    response_model=HealthResponse,
    operation_id="healthReady",
    responses={503: {"model": ErrorResponse}},
)
def ready(request: Request, response: Response) -> HealthResponse:
    try:
        check_database(request.app.state.engine)
        probe_private_storage(request.app.state.settings.PRIVATE_STORAGE_ROOT)
    except Exception as error:
        request.app.state.logger.warning(
            "readiness_dependency_failed",
            extra={
                "request_id": str(request.state.request_id),
                "error_code": type(error).__name__,
            },
        )
        raise FoundationError(
            status_code=503,
            code="TEMPORARILY_UNAVAILABLE",
            message="Serviço temporariamente indisponível.",
        ) from error
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return HealthResponse(status="ok")
