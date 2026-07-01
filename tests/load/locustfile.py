"""
Locust load test — run with:
  locust -f tests/load/locustfile.py --host http://localhost:8000 --users 50 --spawn-rate 10 --run-time 60s --headless
"""
from locust import HttpUser, between, task


class BurstUser(HttpUser):
    """Simulates a user who hammers the API in short bursts."""
    wait_time = between(0.01, 0.1)

    @task(3)
    def hit_public(self):
        self.client.get("/demo/public", name="/demo/public")

    @task(1)
    def hit_burst(self):
        self.client.get("/demo/burst", name="/demo/burst")


class SteadyUser(HttpUser):
    """Simulates a well-behaved user at a steady rate."""
    wait_time = between(0.5, 2.0)

    @task
    def hit_authenticated(self):
        self.client.get(
            "/demo/authenticated",
            headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyXzEyMyJ9.fake"},
            name="/demo/authenticated",
        )

    @task
    def hit_tiered(self):
        self.client.get(
            "/demo/tiered",
            headers={"X-User-Tier": "pro"},
            name="/demo/tiered",
        )

    @task
    def check_health(self):
        self.client.get("/health", name="/health")
