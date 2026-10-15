"""Things every MacroScope service needs.

That covers setting up logging, adding the X-Served-By header, the /health, /ready and /version
endpoints, and replying with a clear 503 when the database is down.

Every service has its own copy of this file rather than sharing one. That keeps each service
completely independent, so it can be built and deployed on its own.
"""
import logging
import socket

import psycopg
import psycopg_pool
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

from app import config
from app.db import check_db

# In Docker this is the container ID. On Kubernetes it's the pod name.
HOSTNAME = socket.gethostname()

log = logging.getLogger(config.SERVICE_NAME)


def setup_logging():
    logging.basicConfig(
        level=config.LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def install_common(app: FastAPI):
    @app.middleware("http")
    async def add_served_by(request: Request, call_next):
        # Tag every response with the container that handled it
        response = await call_next(request)
        response.headers["X-Served-By"] = HOSTNAME
        return response

    @app.exception_handler(psycopg.OperationalError)
    @app.exception_handler(psycopg_pool.PoolTimeout)
    async def database_down(request: Request, exc: Exception):
        # If we can't reach the database, say so clearly rather than throwing a generic 500
        log.error("database unavailable: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"detail": "Database unavailable, please retry shortly"},
            headers={"X-Served-By": HOSTNAME},
        )


health_router = APIRouter(tags=["ops"])


@health_router.get("/health")
def health():
    """Is the service running at all?

    This deliberately doesn't check the database. If the database goes down, we don't want
    Kubernetes restarting a service that's actually fine.
    """
    return {"status": "ok"}


@health_router.get("/ready")
def ready():
    """Is the service ready to handle requests? Only if it can reach its own database."""
    try:
        check_db()
    except Exception as exc:
        log.warning("not ready: %s", exc)
        return JSONResponse(status_code=503, content={"status": "not ready", "reason": "database unavailable"})
    return {"status": "ready"}


@health_router.get("/version")
def version():
    return {"service": config.SERVICE_NAME, "version": config.APP_VERSION, "served_by": HOSTNAME}
