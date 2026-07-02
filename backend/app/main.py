import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.redis_client import close_redis, init_redis
from app.db.seed import seed_demo_rules
from app.db.session import close_db

logging.basicConfig(level=get_settings().log_level)
logger = logging.getLogger(__name__)


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

    # Middleware runs in reverse order of registration: the LAST added is the
    # OUTERMOST (runs first). We register the rate limiter first, then CORS, so
    # CORS ends up outermost. That matters because:
    #   - CORS answers preflight OPTIONS requests before the limiter sees them
    #   - a 429 from the limiter still passes back out through CORS, so the
    #     browser gets CORS headers even on blocked requests
    from app.middleware.rate_limit import RateLimitMiddleware
    app.add_middleware(RateLimitMiddleware)

    # CORS — the React UI runs on a different origin (its own container/port)
    # and calls this API from the browser. We also expose the X-RateLimit-*
    # headers, since custom response headers are hidden from fetch() by default.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
            "X-RateLimit-Policy",
            "X-RateLimit-Retry-After",
            "Retry-After",
        ],
    )

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

    return app


app = create_app()
