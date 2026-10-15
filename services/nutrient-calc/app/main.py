"""nutrient-calc: works out the nutrients in the food people eat, and keeps each user's daily totals."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import config, db, routes
from app.common import health_router, install_common, setup_logging

setup_logging()
log = logging.getLogger(config.SERVICE_NAME)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once when the service starts...
    if len(config.JWT_SECRET) < 32:
        raise RuntimeError("JWT_SECRET must be set and at least 32 characters long")
    db.open_pool()
    log.info("%s %s starting", config.SERVICE_NAME, config.APP_VERSION)
    yield
    # ...and this part runs when it's told to stop, after uvicorn has finished the requests it was handling
    log.info("shutting down, closing database pool")
    db.close_pool()


app = FastAPI(
    title=config.SERVICE_NAME,
    version=config.APP_VERSION,
    lifespan=lifespan,
    # Put the Swagger docs under our own path so they also work through the gateway
    docs_url=f"{config.API_PREFIX}/docs",
    openapi_url=f"{config.API_PREFIX}/openapi.json",
)
install_common(app)

# /health, /ready and /version at the root, where Docker and Kubernetes check them...
app.include_router(health_router)
# ...and the same again under our path, so they can be reached through the gateway (the website footer uses /version)
app.include_router(health_router, prefix=config.API_PREFIX)
app.include_router(routes.router, prefix=config.API_PREFIX)
