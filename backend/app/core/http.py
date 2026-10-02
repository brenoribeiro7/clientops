from fastapi import Request, Response

from app.core.errors import FoundationError


def etag(version: int) -> str:
    return f'"v{version}"'


def require_if_match(request: Request, current_version: int) -> None:
    check_if_match(request.headers.get("if-match"), current_version)


def check_if_match(supplied: str | None, current_version: int) -> None:
    if supplied is None:
        raise FoundationError(
            status_code=428,
            code="PRECONDITION_REQUIRED",
            message="Envie If-Match com a versão atual.",
        )
    if supplied != etag(current_version):
        raise FoundationError(
            status_code=412,
            code="VERSION_CONFLICT",
            message="O recurso foi alterado.",
            details={"current_version": current_version},
            headers={"ETag": etag(current_version)},
        )


def set_resource_headers(response: Response, version: int) -> None:
    response.headers["ETag"] = etag(version)
    response.headers["Cache-Control"] = "no-store"
