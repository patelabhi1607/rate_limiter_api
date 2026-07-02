import type { EndpointConfig, RateLimitResult } from "./types";
import { findEndpoint } from "./endpoints";

// Client-side implementations of the same four algorithms the backend runs in
// Redis Lua. Used as a fallback so the dashboard works as a standalone static
// page when no backend is reachable.

interface SlidingState {
  hits: number[];
}
interface FixedState {
  boundary: number;
  count: number;
}
interface TokenState {
  tokens: number;
  last: number;
}
interface LeakyState {
  queue: number;
  last: number;
}
type AlgoState = SlidingState | FixedState | TokenState | LeakyState;

const state: Record<string, AlgoState> = {};

const nowSec = () => Date.now() / 1000;

function build(
  status: number,
  cfg: EndpointConfig,
  remaining: number,
  reset: number,
  retry: number | null = null,
): RateLimitResult {
  return {
    status,
    limit: cfg.limit,
    remaining,
    reset: Math.ceil(reset),
    policy: `${cfg.limit};w=${cfg.window}`,
    retry: retry != null ? Math.ceil(retry) : null,
  };
}

export function simulate(path: string): RateLimitResult {
  const cfg = findEndpoint(path);
  const now = nowSec();

  if (cfg.algo === "sliding_window") {
    const st = (state[path] as SlidingState) ?? (state[path] = { hits: [] });
    st.hits = st.hits.filter((t) => t > now - cfg.window);
    if (st.hits.length < cfg.limit) {
      st.hits.push(now);
      return build(200, cfg, cfg.limit - st.hits.length, now + cfg.window);
    }
    const retry = st.hits[0] + cfg.window - now;
    return build(429, cfg, 0, now + retry, retry);
  }

  if (cfg.algo === "fixed_window") {
    const boundary = Math.floor(now / cfg.window) * cfg.window + cfg.window;
    let st = state[path] as FixedState | undefined;
    if (!st || st.boundary !== boundary) st = state[path] = { boundary, count: 0 };
    if (st.count < cfg.limit) {
      st.count++;
      return build(200, cfg, cfg.limit - st.count, boundary);
    }
    return build(429, cfg, 0, boundary, boundary - now);
  }

  if (cfg.algo === "token_bucket") {
    const cap = Math.floor(cfg.limit * (cfg.burst ?? 1));
    const rate = cfg.limit / cfg.window;
    const st = (state[path] as TokenState) ?? (state[path] = { tokens: cap, last: now });
    st.tokens = Math.min(cap, st.tokens + (now - st.last) * rate);
    st.last = now;
    if (st.tokens >= 1) {
      st.tokens -= 1;
      return build(200, cfg, Math.floor(st.tokens), now + (cap - st.tokens) / rate);
    }
    const retry = (1 - st.tokens) / rate;
    return build(429, cfg, 0, now + retry, retry);
  }

  // leaky_bucket
  const rate = cfg.limit / cfg.window;
  const st = (state[path] as LeakyState) ?? (state[path] = { queue: 0, last: now });
  const leaked = Math.floor((now - st.last) * rate);
  if (leaked > 0) {
    st.queue = Math.max(0, st.queue - leaked);
    st.last = now;
  }
  if (st.queue < cfg.limit) {
    st.queue++;
    return build(200, cfg, cfg.limit - st.queue, now + st.queue / rate);
  }
  return build(429, cfg, 0, now + 1 / rate, 1 / rate);
}
