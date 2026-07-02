import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.redis_client import close_redis, init_redis
from app.db.seed import seed_demo_rules
from app.db.session import close_db

logging.basicConfig(level=get_settings().log_level)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_redis()
    await seed_demo_rules()
    logger.info("Rate Limiter API started")
    yield
    await close_redis()
    await close_db()
    logger.info("Rate Limiter API shut down")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Rate Limiter API",
        description="Production-grade rate limiting — Token Bucket, Sliding Window, Fixed Window, Leaky Bucket",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Register middleware (outermost = last registered)
    from app.middleware.rate_limit import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware)

    # Routers
    from app.api.health import router as health_router
    from app.api.metrics import router as metrics_router
    from app.api.demo import router as demo_router
    from app.api.admin import router as admin_router

    app.include_router(health_router)
    if settings.metrics_enabled:
        app.include_router(metrics_router)
    app.include_router(demo_router)
    app.include_router(admin_router)

    # Serve the interactive demo dashboard at "/"
    @app.get("/", include_in_schema=False)
    async def dashboard():
        return FileResponse(STATIC_DIR / "index.html")

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app


app = create_app()
