"""ASGI limits apply before multipart parsing and to streamed request bodies."""

import re

from fastapi import HTTPException
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

from app.core.config import settings


class HttpSecurityMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        path = scope["path"]
        upload = bool(re.fullmatch(r"/api/assignments/[0-9]+/project-submissions", path))
        limit = settings.max_project_archive_bytes + 1024 * 1024 if upload else 8 * 1024 * 1024

        async def secured_send(message):
            if message["type"] == "http.response.start":
                out = MutableHeaders(scope=message)
                out["X-Content-Type-Options"] = "nosniff"
                out["X-Frame-Options"] = "DENY"
                out["Referrer-Policy"] = "no-referrer"
                out["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
                out["Content-Security-Policy"] = (
                    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
                )
                out["Cache-Control"] = "private, no-store"
                if settings.app_env == "production" and scope.get("scheme") == "https":
                    out["Strict-Transport-Security"] = "max-age=31536000"
            await send(message)

        async def reject(status, code):
            await JSONResponse({"code": code, "message": code, "details": {}}, status_code=status)(
                scope, receive, secured_send
            )

        # Browser cross-site forms must not reach authentication or mutate state.
        if scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
            origin = headers.get("origin")
            same_origin = f"{scope.get('scheme', 'http')}://{headers.get('host', '')}"
            allowed_origin = origin in settings.cors_origin_list or origin == same_origin
            if (origin and not allowed_origin) or (
                headers.get("sec-fetch-site") == "cross-site" and not allowed_origin
            ):
                return await reject(403, "ORIGIN_NOT_ALLOWED")
        if len(scope.get("query_string", b"")) > 8192 or len(path) > 2048:
            return await reject(414, "REQUEST_URI_TOO_LONG")
        length = headers.get("content-length")
        if length is not None:
            if not length.isascii() or not length.isdigit():
                return await reject(400, "INVALID_CONTENT_LENGTH")
            if int(length) > limit:
                return await reject(413, "REQUEST_TOO_LARGE")
        size = 0

        async def limited_receive():
            nonlocal size
            message = await receive()
            if message["type"] == "http.request":
                size += len(message.get("body", b""))
                if size > limit:
                    raise HTTPException(413, "REQUEST_TOO_LARGE")
            return message

        await self.app(scope, limited_receive, secured_send)
