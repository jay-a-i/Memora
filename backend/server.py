import logging
import sys
import uvicorn
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agent import checkpointer_manager, get_graph
from api import router
from core import settings
from db import engine

log_format = logging.Formatter("%(asctime)s | %(levelname)s | [%(filename)s] | %(message)s")
console_handler = logging.StreamHandler()
file_handler = logging.FileHandler(filename="app_logs.log", mode="a", encoding="utf-8")
console_handler.setFormatter(log_format)
file_handler.setFormatter(log_format)

logging.basicConfig(
    level=logging.INFO,
    handlers=[console_handler, file_handler]
)

logger = logging.getLogger(__name__)


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

app.include_router(router, prefix="/api/v1")


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


def run_server():
    config = uvicorn.Config(
        "server:app",
        host="127.0.0.1",
        port=8000,
        loop="asyncio",
    )
    server = uvicorn.Server(config)

    if sys.platform == "win32":
        with asyncio.Runner(
            loop_factory=asyncio.SelectorEventLoop
        ) as runner:
            try:
                runner.run(server.serve())
            except (KeyboardInterrupt, asyncio.CancelledError):
                pass
    else:
        try:
            server.run()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass

if __name__ == "__main__":
    run_server()