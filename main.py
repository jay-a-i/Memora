import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.agent.checkpointer import checkpointer_manager
from backend.app.agent.orchestrator import get_graph
from backend.app.api.api import api_router
from backend.app.core.config import settings
from backend.app.core.database import engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Opens the checkpointer pool at startup and compiles the graph around it.

    The saver needs a live connection pool, which cannot exist at import time --
    and this module is imported by scripts and tests that never serve requests.
    So the checkpointed graph is built here and published on `app.state`, which
    is what the chat endpoint runs.

    Shutdown closes the pool and disposes the SQLAlchemy engine. Without the
    dispose, every `--reload` cycle and every rolling container stop drops
    in-flight pooled connections instead of draining them.

    A checkpointer that fails to start is logged and tolerated: the app still
    serves chat using caller-supplied history, just without agent-side state.
    """
    saver = await checkpointer_manager.start()
    app.state.checkpointer = saver
    app.state.graph = get_graph(saver)
    app.state.checkpointing = saver is not None

    if saver is None:
        logger.warning(
            "Running WITHOUT LangGraph state persistence. The agent will fall "
            "back to caller-supplied history for each request."
        )
    else:
        logger.info("Agent state persistence enabled (LangGraph + Postgres).")

    try:
        yield
    finally:
        await checkpointer_manager.stop()
        await engine.dispose()
        logger.info("Shutdown complete; checkpointer pool and DB engine closed.")


app = FastAPI(
    title="MEMORA API",
    version=settings.BACKEND_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/", tags=["Health"], summary="Service metadata")
async def root():
    """Unauthenticated service banner, useful for confirming the API is up."""
    return {
        "project": settings.PROJECT_NAME,
        "version": settings.BACKEND_VERSION,
    }


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Returns a generic message instead of a stack trace, which would otherwise
    leak connection strings and file paths to API clients.
    """
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error."},
    )
