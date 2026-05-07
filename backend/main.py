from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.dependencies import InsufficientCreditsHttpError
from backend.api.routers import admin, auth, payments, pipeline, projects, webhooks
from backend.config import get_settings
from backend.db.session import close_default_session_manager


@asynccontextmanager
async def application_lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await close_default_session_manager()


def create_app() -> FastAPI:
    """Create the FastAPI application."""

    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=application_lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allowed_origin_list),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.exception_handler(InsufficientCreditsHttpError)
    async def insufficient_credits_handler(
        _request: Request,
        exc: InsufficientCreditsHttpError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=402,
            content={
                "detail": "Insufficient credits.",
                "required": exc.required,
                "balance": exc.balance,
            },
        )

    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(projects.router)
    app.include_router(payments.router)
    app.include_router(webhooks.router)
    app.include_router(pipeline.router)
    return app


app = create_app()
