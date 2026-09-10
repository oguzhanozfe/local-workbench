from __future__ import annotations

import hmac
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import __version__
from .config import Settings
from .contracts import ChatRequest, TaskRequest
from .runtime import Runtime, WorkbenchError


class BodyLimit:
    def __init__(self, app, limit):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.limit:
                response = JSONResponse(
                    {
                        "error": {
                            "code": "request_too_large",
                            "message": "Request exceeds the configured byte limit.",
                        }
                    },
                    status_code=413,
                )
                return await response(scope, receive, send)
            if not message.get("more_body"):
                break
        delivered = False

        async def buffered():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, buffered, send)


def create_app(settings: Settings, runtime: Runtime | None = None):
    service = runtime or Runtime(settings)

    @asynccontextmanager
    async def lifespan(app):
        yield
        await service.close()

    app = FastAPI(title="Local Workbench", version=__version__, lifespan=lifespan)
    app.state.runtime = service
    app.add_middleware(BodyLimit, limit=settings.max_request_bytes)

    @app.middleware("http")
    async def credentials(request: Request, call_next):
        if settings.api_token_env:
            token = os.environ.get(settings.api_token_env)
            if not token:
                return JSONResponse(
                    {
                        "error": {
                            "code": "server_credentials_missing",
                            "message": "Gateway credential is unavailable.",
                        }
                    },
                    status_code=503,
                )
            supplied = request.headers.get("authorization", "")
            if not hmac.compare_digest(supplied, "Bearer " + token):
                return JSONResponse(
                    {
                        "error": {
                            "code": "unauthorized",
                            "message": "A valid bearer token is required.",
                        }
                    },
                    status_code=401,
                )
        return await call_next(request)

    @app.exception_handler(WorkbenchError)
    async def rejected(request: Request, exc: WorkbenchError):
        return JSONResponse(
            {
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "status": "unreviewed_draft",
                }
            },
            status_code=exc.status,
        )

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError):
        # Pydantic errors contain rejected input; do not echo private packets.
        fields = [".".join(str(part) for part in error["loc"]) for error in exc.errors()]
        return JSONResponse(
            {
                "error": {
                    "code": "invalid_request",
                    "message": "Request does not match the API contract.",
                    "fields": fields,
                }
            },
            status_code=422,
        )

    @app.exception_handler(OSError)
    async def storage_error(request: Request, exc: OSError):
        return JSONResponse(
            {
                "error": {
                    "code": "storage_unavailable",
                    "message": "Configured local state storage is unavailable.",
                }
            },
            status_code=503,
        )

    @app.get("/health")
    async def health():
        return await service.health()

    @app.get("/v1/models")
    async def models():
        return {
            "object": "list",
            "data": [
                {"id": alias, "object": "model", "owned_by": "local", "created": 0}
                for alias in settings.models
            ],
        }

    @app.post("/v1/chat/completions")
    async def chat(request: ChatRequest):
        return await service.chat(request)

    @app.post("/v1/tasks")
    async def task(request: TaskRequest):
        return await service.task(request)

    return app
