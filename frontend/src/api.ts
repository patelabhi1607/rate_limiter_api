import type { RateLimitResult } from "./types";
import { findEndpoint } from "./endpoints";

// Base URL of the backend. Configured at build time via Vite env; falls back to
// the local backend container's published port.
export const API_URL: string =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

// A demo (unsigned) JWT with sub=demo_user — the rate limiter only reads the
// `sub` claim, it does not verify the signature.
const DEMO_JWT =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." +
  "eyJzdWIiOiJkZW1vX3VzZXIiLCJyb2xlIjoicHJvIn0.demo_signature";

function headersFor(path: string): Record<string, string> {
  const h: Record<string, string> = {};
  if (path === "/demo/authenticated") h["Authorization"] = "Bearer " + DEMO_JWT;
  if (path === "/demo/api-key") h["X-API-Key"] = "demo-key-123";
  if (path === "/demo/tiered") {
    h["Authorization"] = "Bearer " + DEMO_JWT;
    h["X-User-Tier"] = "pro";
  }
  return h;
}

function normalize(resp: Response): RateLimitResult {
  const limit = parseInt(resp.headers.get("x-ratelimit-limit") ?? "0", 10);
  const rem = resp.headers.get("x-ratelimit-remaining");
  const reset = resp.headers.get("x-ratelimit-reset");
  const retry = resp.headers.get("retry-after");
  return {
    status: resp.status,
    limit,
    remaining: rem != null ? parseInt(rem, 10) : 0,
    reset: reset != null ? parseInt(reset, 10) : 0,
    policy: resp.headers.get("x-ratelimit-policy") ?? "",
    retry: retry != null ? parseInt(retry, 10) : null,
  };
}

/** Call the real backend. Throws if unreachable so the caller can fall back. */
export async function callApi(path: string): Promise<RateLimitResult> {
  const resp = await fetch(API_URL + path, { headers: headersFor(path) });
  return normalize(resp);
}

/** Ping /health to decide whether the real backend is reachable. */
export async function checkBackend(): Promise<boolean> {
  try {
    const r = await fetch(API_URL + "/health");
    return r.ok;
  } catch {
    return false;
  }
}

// Re-export for callers that want endpoint metadata
export { findEndpoint };
