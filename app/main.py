"""FastAPI application entrypoint.

Wires together config, the reusable OpenAI client, rate limiting, structured
logging, and the three required endpoints: /health, /career-map, and
/career-map/compare.
"""

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging, log_request_event
from app.core.rate_limit import InMemoryRateLimiter
from app.models.request import CareerMapCompareRequest, CareerMapRequest
from app.models.response import CareerMapCompareResponse, CareerMapResponse, ErrorDetail, ErrorResponse, HealthResponse
from app.services.career_mapper import create_career_map, create_career_map_comparison
from app.services.openai_client import OpenAIClient

settings = get_settings()
configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One reusable OpenAI client for the whole app lifetime -- connections are
    # pooled instead of opened per request.
    app.state.openai_client = OpenAIClient(settings)
    app.state.rate_limiter = InMemoryRateLimiter(max_requests=settings.rate_limit_per_minute, window_seconds=60.0)
    yield
    await app.state.openai_client.aclose()


app = FastAPI(
    title=settings.app_name,
    description="Maps a course syllabus to a target career: matched skills, gaps, "
    "projects, and a week-by-week learning plan, grounded in syllabus evidence.",
    version="1.0.0",
    lifespan=lifespan,
)


def _new_request_id() -> str:
    return str(uuid.uuid4())


def _error_envelope(error_code: str, message: str, request_id: str, details: list[ErrorDetail] | None = None) -> dict:
    return ErrorResponse(error_code=error_code, message=message, request_id=request_id, details=details).model_dump(
        mode="json"
    )


_MAX_BODY_BYTES = 200_000  # generous ceiling above the 20k-char syllabus limit, accounting for JSON overhead


@app.middleware("http")
async def add_request_id_and_rate_limit(request: Request, call_next):
    request_id = _new_request_id()
    request.state.request_id = request_id
    start = time.perf_counter()

    # Reject oversized bodies before they're parsed at all.
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > _MAX_BODY_BYTES:
        elapsed_ms = (time.perf_counter() - start) * 1000
        log_request_event(request_id, request.url.path, 413, elapsed_ms, error_code="PAYLOAD_TOO_LARGE")
        return JSONResponse(
            status_code=413,
            content=_error_envelope(
                "PAYLOAD_TOO_LARGE", "The request body is too large. Reduce the syllabus length and try again.", request_id
            ),
        )

    # Health checks are exempt from rate limiting.
    if request.url.path != "/health":
        client_key = request.client.host if request.client else "unknown"
        if not request.app.state.rate_limiter.check(client_key):
            elapsed_ms = (time.perf_counter() - start) * 1000
            log_request_event(request_id, request.url.path, 429, elapsed_ms, error_code="RATE_LIMIT_EXCEEDED")
            return JSONResponse(
                status_code=429,
                content=_error_envelope(
                    "RATE_LIMIT_EXCEEDED", "Too many requests. Please slow down and try again shortly.", request_id
                ),
            )

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# --- Global exception handlers -------------------------------------------------------------


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", _new_request_id())
    details = [
        ErrorDetail(field=".".join(str(p) for p in err["loc"] if p != "body"), message=err["msg"])
        for err in exc.errors()
    ]
    elapsed_ms = 0.0
    log_request_event(request_id, request.url.path, 422, elapsed_ms, error_code="VALIDATION_ERROR")
    return JSONResponse(
        status_code=422,
        content=_error_envelope("VALIDATION_ERROR", "One or more request fields are invalid.", request_id, details),
    )


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    request_id = getattr(request.state, "request_id", _new_request_id())
    log_request_event(request_id, request.url.path, exc.status_code, 0.0, error_code=exc.error_code)
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_envelope(exc.error_code, exc.message, request_id),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", _new_request_id())
    log_request_event(request_id, request.url.path, 500, 0.0, error_code="INTERNAL_ERROR")
    # Never leak stack traces or exception internals to the client.
    return JSONResponse(
        status_code=500,
        content=_error_envelope(
            "INTERNAL_ERROR", "An unexpected error occurred. Please try again later.", request_id
        ),
    )


# --- Routes ----------------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    """Confirms the API is running. Exposes no secrets or internal state."""
    return HealthResponse(status="ok", app_name=settings.app_name, environment=settings.environment)


@app.post("/career-map", response_model=CareerMapResponse, tags=["career-map"])
async def career_map(payload: CareerMapRequest, request: Request) -> CareerMapResponse:
    request_id = request.state.request_id
    start = time.perf_counter()

    result = await create_career_map(request.app.state.openai_client, payload, request_id)

    elapsed_ms = (time.perf_counter() - start) * 1000
    log_request_event(
        request_id,
        "/career-map",
        200,
        elapsed_ms,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
    )
    return result


@app.post("/career-map/compare", response_model=CareerMapCompareResponse, tags=["career-map"])
async def career_map_compare(payload: CareerMapCompareRequest, request: Request) -> CareerMapCompareResponse:
    request_id = request.state.request_id
    start = time.perf_counter()

    result = await create_career_map_comparison(request.app.state.openai_client, payload, request_id)

    elapsed_ms = (time.perf_counter() - start) * 1000
    log_request_event(
        request_id,
        "/career-map/compare",
        200,
        elapsed_ms,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
    )
    return result
