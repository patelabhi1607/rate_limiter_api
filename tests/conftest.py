"""
Shared fixtures using testcontainers for real Redis + PostgreSQL.
Only loaded when integration tests actually request them (no autouse).
"""
import os
import pytest
import redis.asyncio as aioredis
from httpx import ASGITransport, AsyncClient
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def redis_container():
    with RedisContainer("redis:7-alpine") as rc:
        yield rc


@pytest.fixture(scope="session")
def db_url(postgres_container):
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    user = postgres_container.username
    password = postgres_container.password
    db = postgres_container.dbname
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


@pytest.fixture(scope="session")
def redis_url(redis_container):
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"


@pytest.fixture
async def redis_client(redis_url):
    client = aioredis.from_url(redis_url, decode_responses=False)
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.fixture(scope="session")
async def app_with_db(db_url, redis_url):
    """Session-scoped app with real DB and Redis, migrations applied."""
    os.environ["DATABASE_URL"] = db_url
    os.environ["REDIS_URL"] = redis_url
    os.environ["ADMIN_API_KEY"] = "test-admin-key"
    os.environ["REDIS_FAIL_OPEN"] = "true"

    from app.core.config import get_settings
    get_settings.cache_clear()

    # Run migrations
    import subprocess
    subprocess.run(
        ["python", "-m", "alembic", "upgrade", "head"],
        env={**os.environ, "DATABASE_URL": db_url},
        check=True,
    )

    from app.main import create_app
    return create_app()


@pytest.fixture
async def client(app_with_db):
    async with AsyncClient(
        transport=ASGITransport(app=app_with_db), base_url="http://test"
    ) as c:
        yield c
