"""
Concurrency test: fire 100 simultaneous requests; exactly `limit` should pass.
"""
import asyncio
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.integration
async def test_exactly_n_requests_pass(app_with_db, redis_client):
    """With limit=10, exactly 10 of 100 concurrent requests must pass."""
    LIMIT = 10
    TOTAL = 100

    # Set a rule with a tight limit
    async with AsyncClient(
        transport=ASGITransport(app=app_with_db), base_url="http://test"
    ) as admin:
        resp = await admin.post(
            "/admin/rules",
            json={
                "name": "concurrent-test-rule",
                "route_pattern": "/demo/public",
                "algorithm": "sliding_window",
                "limit": LIMIT,
                "window_seconds": 3600,
                "dimension": "ip",
                "priority": 999,
            },
            headers={"X-Admin-Key": "test-admin-key"},
        )
        assert resp.status_code == 201

    await redis_client.flushdb()

    async with AsyncClient(
        transport=ASGITransport(app=app_with_db), base_url="http://test"
    ) as c:
        tasks = [c.get("/demo/public") for _ in range(TOTAL)]
        results = await asyncio.gather(*tasks)

    passed = sum(1 for r in results if r.status_code == 200)
    blocked = sum(1 for r in results if r.status_code == 429)

    assert passed == LIMIT, f"Expected {LIMIT} to pass, got {passed}"
    assert blocked == TOTAL - LIMIT, f"Expected {TOTAL - LIMIT} blocked, got {blocked}"

    # Cleanup
    async with AsyncClient(
        transport=ASGITransport(app=app_with_db), base_url="http://test"
    ) as admin:
        rules = (await admin.get("/admin/rules", headers={"X-Admin-Key": "test-admin-key"})).json()
        for rule in rules["items"]:
            if rule["name"] == "concurrent-test-rule":
                await admin.delete(
                    f"/admin/rules/{rule['id']}", headers={"X-Admin-Key": "test-admin-key"}
                )
