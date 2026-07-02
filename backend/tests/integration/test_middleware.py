"""Integration tests for the rate-limit middleware — requires real Redis + Postgres."""
import pytest


@pytest.mark.integration
class TestHealthEndpoint:
    async def test_health_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["api"] == "ok"

    async def test_health_has_all_keys(self, client):
        resp = await client.get("/health")
        data = resp.json()
        assert "redis" in data
        assert "postgres" in data
        assert "status" in data


@pytest.mark.integration
class TestDemoEndpoints:
    async def test_demo_public_returns_200(self, client):
        resp = await client.get("/demo/public")
        assert resp.status_code == 200

    async def test_ratelimit_headers_present(self, client):
        resp = await client.get("/demo/public")
        assert "x-ratelimit-limit" in resp.headers
        assert "x-ratelimit-remaining" in resp.headers
        assert "x-ratelimit-reset" in resp.headers

    async def test_remaining_decrements(self, client, redis_client):
        await redis_client.flushdb()
        resp1 = await client.get("/demo/public")
        resp2 = await client.get("/demo/public")
        r1 = int(resp1.headers.get("x-ratelimit-remaining", -1))
        r2 = int(resp2.headers.get("x-ratelimit-remaining", -1))
        assert r2 < r1


@pytest.mark.integration
class TestAdminApi:
    HEADERS = {"X-Admin-Key": "test-admin-key"}

    async def test_unauthorized_without_key(self, client):
        resp = await client.get("/admin/rules")
        assert resp.status_code in (401, 403)

    async def test_create_and_get_rule(self, client):
        payload = {
            "name": "test-rule",
            "route_pattern": "/demo/*",
            "algorithm": "sliding_window",
            "limit": 100,
            "window_seconds": 60,
            "dimension": "ip",
        }
        create_resp = await client.post("/admin/rules", json=payload, headers=self.HEADERS)
        assert create_resp.status_code == 201
        rule_id = create_resp.json()["id"]

        get_resp = await client.get(f"/admin/rules/{rule_id}", headers=self.HEADERS)
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "test-rule"

    async def test_patch_rule(self, client):
        payload = {
            "name": "patch-test-rule",
            "route_pattern": "/demo/public",
            "algorithm": "fixed_window",
            "limit": 50,
            "window_seconds": 30,
            "dimension": "ip",
        }
        create_resp = await client.post("/admin/rules", json=payload, headers=self.HEADERS)
        assert create_resp.status_code == 201
        rule_id = create_resp.json()["id"]

        patch_resp = await client.patch(
            f"/admin/rules/{rule_id}", json={"enabled": False}, headers=self.HEADERS
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["enabled"] is False

    async def test_delete_rule(self, client):
        payload = {
            "name": "delete-test-rule",
            "route_pattern": "/demo/strict",
            "algorithm": "leaky_bucket",
            "limit": 10,
            "window_seconds": 60,
            "dimension": "ip",
        }
        create_resp = await client.post("/admin/rules", json=payload, headers=self.HEADERS)
        rule_id = create_resp.json()["id"]

        del_resp = await client.delete(f"/admin/rules/{rule_id}", headers=self.HEADERS)
        assert del_resp.status_code == 204

        get_resp = await client.get(f"/admin/rules/{rule_id}", headers=self.HEADERS)
        assert get_resp.status_code == 404
