# Rate Limiter API

Production-grade HTTP rate limiting service built with FastAPI and Redis. Supports 4 algorithms, per-route rules, per-user-tier limits, full admin CRUD, Prometheus metrics, and audit logging.

## Algorithms

| Algorithm | Burst? | Memory | Best For |
|---|---|---|---|
| **Sliding Window** | No | O(n) | Strict per-IP limiting |
| **Token Bucket** | Yes (configurable) | O(1) | API key quotas |
| **Fixed Window** | At boundary | O(1) | Simple counters |
| **Leaky Bucket** | No | O(1) | Constant output rate |

All algorithms are implemented as **Lua scripts** executed atomically inside Redis — zero TOCTOU race conditions.

## Features

- **4 algorithms** switchable per route via admin API
- **Per-IP, per-user, per-API-key, per-tier, or global** limiting dimensions
- **Tier-based limits** — `free/pro/enterprise` get different quotas from the same rule
- **IETF-standard response headers** — `X-RateLimit-Limit/Remaining/Reset/Policy`
- **Redis fail-open or fail-closed** — configurable behavior when Redis is down
- **Clock-skew-safe** — uses Redis `TIME` command, never the server clock
- **Admin REST API** — full CRUD for rules, whitelist, blacklist, counter reset, audit log
- **Prometheus metrics** at `/metrics`
- **Audit logging** to PostgreSQL (async, non-blocking via `asyncio.create_task`)
- **Multi-stage Docker build** + Docker Compose for one-command start

## Quick Start

```bash
cp .env.example .env
docker-compose up
```

API available at `http://localhost:8000`. Prometheus at `http://localhost:9090`.

## Interactive Dashboard

Open **`http://localhost:8000/`** for a live demo dashboard where you can fire
single or burst requests at each demo endpoint and watch requests get allowed
(green) or blocked (red) in real time, with the live `X-RateLimit-*` headers and
a quota bar.

The dashboard also runs **standalone** — if no backend is reachable it falls back
to a client-side simulator implementing the same four algorithms in JavaScript, so
the page works even when hosted as a static file.

## Demo Endpoints

```
GET /demo/public        Per-IP 10/min, sliding window
GET /demo/authenticated Per-user 100/min, token bucket (Bearer JWT)
GET /demo/api-key       Per-key 50/min, fixed window (X-API-Key header)
GET /demo/tiered        free=5 / pro=50 / enterprise=500 per min (X-User-Tier header)
GET /demo/burst         Token bucket with 2× burst allowance
GET /demo/strict        Leaky bucket — 1 req/sec output rate
```

## Admin API

All endpoints require `X-Admin-Key` header.

```
POST   /admin/rules              Create rule
GET    /admin/rules              List rules (paginated)
PUT    /admin/rules/{id}         Full update
PATCH  /admin/rules/{id}         Partial update (e.g. toggle enabled)
DELETE /admin/rules/{id}         Delete
POST   /admin/rules/{id}/disable Disable rule
POST   /admin/rules/{id}/enable  Re-enable rule

DELETE /admin/counters/{client}  Reset Redis counters (SCAN-safe)
GET    /admin/quota/{client}     View current keys without modifying

POST   /admin/whitelist          Add IP or API key to whitelist
DELETE /admin/whitelist/{id}
POST   /admin/blacklist          Add to blacklist (supports expires_at)
DELETE /admin/blacklist/{id}

GET    /admin/audit              Query violation log (filter by IP, route, time range)
```

## Example: Create a Rule

```bash
curl -X POST http://localhost:8000/admin/rules \
  -H "X-Admin-Key: change-me-in-production" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "api-sliding-window",
    "route_pattern": "/api/*",
    "algorithm": "sliding_window",
    "limit": 60,
    "window_seconds": 60,
    "dimension": "ip",
    "priority": 10
  }'
```

## Response Headers

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 43
X-RateLimit-Reset: 1720000060
X-RateLimit-Policy: 100;w=60
X-RateLimit-Retry-After: 17   ← only on 429
```

## Configuration (.env)

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | postgres://... | Async PostgreSQL URL |
| `REDIS_URL` | redis://... | Redis connection |
| `REDIS_FAIL_OPEN` | `true` | Allow requests when Redis is down |
| `TRUSTED_PROXY_HOPS` | `1` | How many rightmost X-Forwarded-For hops to trust |
| `DEFAULT_ALGORITHM` | `sliding_window` | Fallback algorithm (no matching rule) |
| `DEFAULT_LIMIT` | `100` | Fallback limit |
| `DEFAULT_WINDOW_SECONDS` | `60` | Fallback window |
| `ADMIN_API_KEY` | — | Required for all `/admin/*` endpoints |
| `WHITELIST_IPS` | — | Comma-separated IPs that bypass limiting |
| `BLACKLIST_IPS` | — | Comma-separated IPs that are always blocked |

## Running Tests

```bash
pip install -r requirements.txt

# Unit tests (no containers)
pytest -m unit -v

# Integration tests (starts Redis + Postgres via testcontainers)
pytest -m integration -v

# Load test (requires running server)
locust -f tests/load/locustfile.py --host http://localhost:8000 \
  --users 50 --spawn-rate 10 --run-time 60s --headless
```

## Tech Stack

- **FastAPI** — async web framework
- **Redis 7** (`redis[asyncio]`) — Lua-script atomic rate limiting
- **PostgreSQL 16** — rule storage and audit logs
- **SQLAlchemy 2 async** + **Alembic** — ORM and migrations
- **prometheus-client** — `/metrics` endpoint
- **testcontainers** — real Redis/Postgres in integration tests
- **Locust** — load testing
- **Docker** — multi-stage build

## Project Structure

```
app/
  algorithms/        Token bucket, sliding window, fixed window, leaky bucket
  api/               demo, admin, metrics, health routers
  core/              config, redis client, Lua scripts, IP utils
  db/                SQLAlchemy models, async session, Alembic migrations
  middleware/        RateLimitMiddleware (enforcement)
  schemas/           Pydantic request/response models
tests/
  unit/              Fast tests, mocked Redis
  integration/       Full HTTP tests with testcontainers
  load/              Locust load scenarios
```
