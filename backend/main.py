from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.api.routers import auth, pipeline, projects
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

    @app.get("/healthz")
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(projects.router)
    app.include_router(pipeline.router)
    return app


app = create_app()
