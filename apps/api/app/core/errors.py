from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def problem(status: int, title: str, detail: Any = None, **extra: Any) -> JSONResponse:
    body: dict[str, Any] = {"type": "about:blank", "title": title, "status": status}
    if detail is not None:
        body["detail"] = detail
    body.update(extra)
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


def not_found(what: str = "Resource") -> HTTPException:
    """Foreign-tenant and inaccessible objects deliberately look identical to missing ones."""
    return HTTPException(status_code=404, detail=f"{what} not found")


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        resp = problem(exc.status_code, _title(exc.status_code), exc.detail,
                       request_id=getattr(request.state, "request_id", None))
        if exc.headers:
            resp.headers.update(exc.headers)
        return resp

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
        return problem(422, "Validation failed", errors=errors, request_id=getattr(request.state, "request_id", None))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        return problem(500, "Internal Server Error", "An unexpected error occurred.",
                       request_id=getattr(request.state, "request_id", None))


def _title(status: int) -> str:
    return {400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found", 409: "Conflict",
            422: "Validation failed", 429: "Too Many Requests"}.get(status, "Error")
