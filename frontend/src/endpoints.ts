import type { EndpointConfig } from "./types";

// Mirrors the seeded rules in the backend (app/db/seed.py). Used both to label
// the UI and to drive the client-side simulator when no backend is reachable.
export const ENDPOINTS: EndpointConfig[] = [
  {
    path: "/demo/public",
    label: "/demo/public — 10/min per IP (sliding window)",
    desc: "No auth needed. Each unique IP gets 10 requests per minute. Sliding window prevents boundary bursts.",
    algo: "sliding_window",
    limit: 10,
    window: 60,
  },
  {
    path: "/demo/authenticated",
    label: "/demo/authenticated — 100/min per user (token bucket)",
    desc: "Sends a demo Bearer token. 100 req/min per user via token bucket — unused quota accumulates.",
    algo: "token_bucket",
    limit: 100,
    window: 60,
  },
  {
    path: "/demo/api-key",
    label: "/demo/api-key — 50/min per key (fixed window)",
    desc: "Sends an X-API-Key header. 50 req/min per key using a fixed window that resets on the minute.",
    algo: "fixed_window",
    limit: 50,
    window: 60,
  },
  {
    path: "/demo/tiered",
    label: "/demo/tiered — free=5 / pro=50 / enterprise=500",
    desc: "Sends X-User-Tier: pro. Different tiers get different limits from the same rule.",
    algo: "sliding_window",
    limit: 50, // pro tier
    window: 60,
  },
  {
    path: "/demo/burst",
    label: "/demo/burst — token bucket, 2× burst",
    desc: "Token bucket with 2× burst multiplier — allows a short spike above the steady rate.",
    algo: "token_bucket",
    limit: 10,
    window: 60,
    burst: 2.0,
  },
  {
    path: "/demo/strict",
    label: "/demo/strict — leaky bucket, 1/sec",
    desc: "Leaky bucket — drains at exactly 1 request/second, no bursts allowed.",
    algo: "leaky_bucket",
    limit: 1,
    window: 1,
  },
];

export function findEndpoint(path: string): EndpointConfig {
  return ENDPOINTS.find((e) => e.path === path) ?? ENDPOINTS[0];
}
