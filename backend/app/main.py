from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException

from app.api.router import api_router, internal_router
from app.core.config import settings

app = FastAPI(title=settings.app_name, version="0.1.0")


@app.exception_handler(HTTPException)
async def http_error(_request: Request, exc: HTTPException):
    detail = exc.detail
    code = detail.get("code", "REQUEST_FAILED") if isinstance(detail, dict) else str(detail)
    details = {k: v for k, v in detail.items() if k != "code"} if isinstance(detail, dict) else {}
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": code,
            "message": code,
            "details": details,
            # Keep the legacy field while student-facing clients transition to code/details.
            "detail": detail,
        },
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    # Do not echo input values: requests can contain passwords or personal data.
    details = [
        {"field": list(error["loc"]), "message": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": "Invalid request fields",
            "details": {"errors": details},
        },
    )


@app.exception_handler(IntegrityError)
async def integrity_error(_request: Request, _exc: IntegrityError):
    return JSONResponse(
        status_code=409,
        content={
            "code": "CONFLICT",
            "message": "The operation conflicts with existing records",
            "details": {},
        },
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix=settings.api_prefix)
app.include_router(internal_router, prefix="/internal")
