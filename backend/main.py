#backend/main.py

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.agent.checkpointer import checkpointer_manager
from src.agent.orchestrator import get_graph
from src.api.api import api_router
from src.core.config import settings
from src.core.database import engine


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

from fastapi import FastAPI
import logging

logger = logging.getLogger("uvicorn.error")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Opens the checkpointer pool at startup and compiles the graph around it.
    Closes the DB engine cleanly and shutdowns if the checkpointer fails to initialize.
    """
    try:
        saver = await checkpointer_manager.start()        
        if saver is None:
            logger.critical("CRITICAL: checkpointer_manager.start() returned None. Persistence is required.")
            await engine.dispose()
            raise SystemExit(1)
            
    except SystemExit:
        # Re-raise SystemExit so it isn't swallowed by the generic Exception block below
        raise
    except Exception as e:
        logger.critical(f"CRITICAL: Failed to start checkpointer manager due to error: {e}")
        try:
            await engine.dispose()
        except Exception as dispose_err:
            logger.error(f"Failed to dispose engine during crash cleanup: {dispose_err}")
        raise SystemExit(1)
    
    app.state.checkpointer = saver
    logger.info("Checkpointer Initialized")
    
    app.state.graph = get_graph(saver)
    logger.info("Graph Compiled")

    try:
        logger.info("Backend successfully started.")
        yield
    finally:
        # Standard graceful shutdown when the app stops normally (e.g., Ctrl+C, SIGTERM)
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


if __name__ == "__main__":
    import uvicorn

    if sys.platform == "win32":

        """
        Windows defaults to asyncio:ProactorEventLoop which is not compatible
        with psycopg (psycopg 3) and throws RuntimeError in runtime,
        so changing it to asyncio:Selector-styleEventLoop, so app runs smoothly.
        """

        uvicorn.run("main:app", host="127.0.0.1", port=8000, loop="asyncio:SelectorEventLoop")
    else:
        """
        Linux/Mac defaults to asyncio:Selector-styleEventLoop, so app is already running smoothly.
        """
        uvicorn.run("main:app", host="127.0.0.1", port=8000)