from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorItem(BaseModel):
    field: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    fields: list[ErrorItem] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class FoundationError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = dict(details or {})
        self.headers = dict(headers or {})


def _request_id(request: Request) -> str:
    return str(request.state.request_id)


def _response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    fields: Sequence[ErrorItem] = (),
    details: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            fields=list(fields),
            details=dict(details or {}),
            request_id=_request_id(request),
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            **dict(headers or {}),
        },
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(FoundationError)
    async def foundation_error(request: Request, error: FoundationError) -> JSONResponse:
        return _response(
            request,
            status_code=error.status_code,
            code=error.code,
            message=error.message,
            details=error.details,
            headers=error.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        fields = [
            ErrorItem(
                field=".".join(
                    str(item) for item in issue["loc"] if item not in {"body", "query", "path"}
                ),
                message="Valor inválido.",
            )
            for issue in error.errors()
        ]
        return _response(
            request,
            status_code=422,
            code="VALIDATION_ERROR",
            message="Revise os campos informados.",
            fields=fields,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        if error.status_code == 404:
            return _response(
                request,
                status_code=404,
                code="NOT_FOUND",
                message="Recurso não encontrado.",
            )
        return _response(
            request,
            status_code=error.status_code,
            code="HTTP_ERROR",
            message="Não foi possível processar a solicitação.",
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
        request.app.state.logger.exception(
            "unexpected_request_error",
            extra={"request_id": _request_id(request), "error_code": "INTERNAL_ERROR"},
        )
        return _response(
            request,
            status_code=500,
            code="INTERNAL_ERROR",
            message="Ocorreu um erro interno.",
        )
