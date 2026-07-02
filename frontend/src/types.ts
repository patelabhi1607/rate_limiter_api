// Shared types for the rate-limiter dashboard.

export type Algorithm =
  | "sliding_window"
  | "token_bucket"
  | "fixed_window"
  | "leaky_bucket";

export interface EndpointConfig {
  path: string;
  label: string;
  desc: string;
  algo: Algorithm;
  limit: number;
  window: number;
  burst?: number;
}

// A normalized rate-limit result, whether from the real API or the simulator.
export interface RateLimitResult {
  status: number;
  limit: number;
  remaining: number;
  reset: number;
  policy: string;
  retry: number | null;
}

export interface LogEntry {
  id: number;
  status: number | "ERR";
  path: string;
  remaining: number | null;
  time: string;
}
