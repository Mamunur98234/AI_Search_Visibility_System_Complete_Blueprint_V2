import logging
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errors import install_error_handlers, problem
from app.core.security import constant_time_equals
from app.routers import auth, crawl, crm, reference, tenancy

API_PREFIX = "/api/v1"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Every API router. tests/test_route_permissions.py walks these to enforce access declarations.
ROUTERS = [reference.health_router, auth.router, tenancy.router, crm.router, crawl.router, reference.router]

logging.basicConfig(level=logging.INFO, format='{"level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="AI Search Visibility System API",
        version="0.1.0",
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=None if s.is_production else f"{API_PREFIX}/docs",
        redoc_url=None,
    )
    install_error_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Invitation-Token", "X-Request-ID"],
    )

    @app.middleware("http")
    async def security_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        rid = request.headers.get("x-request-id", "")
        request.state.request_id = rid if 8 <= len(rid) <= 64 and rid.replace("-", "").isalnum() else uuid.uuid4().hex

        if request.method in UNSAFE_METHODS and request.url.path.startswith(API_PREFIX):
            # 1) Origin check: browsers always send Origin on cross-site unsafe requests.
            origin = request.headers.get("origin")
            if origin is not None and origin.rstrip("/") not in s.origins:
                return problem(403, "Forbidden", "Cross-origin request rejected", request_id=request.state.request_id)
            # 2) Double-submit CSRF token.
            cookie = request.cookies.get(s.csrf_cookie_name, "")
            header = request.headers.get("x-csrf-token", "")
            if not cookie or not header or not constant_time_equals(cookie, header):
                return problem(403, "Forbidden", "Missing or invalid CSRF token",
                               request_id=request.state.request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        if not request.url.path.endswith("/docs"):
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        if request.url.path.startswith(API_PREFIX):
            response.headers["Cache-Control"] = "no-store"
        if s.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response

    for r in ROUTERS:
        app.include_router(r, prefix=API_PREFIX)
    return app


app = create_app()
