import type { RateLimitResult } from "../types";

interface Props {
  last: RateLimitResult | null;
  allowed: number;
  blocked: number;
}

function quotaColor(pct: number): string {
  if (pct > 50) return "linear-gradient(90deg, var(--green), var(--yellow))";
  if (pct > 20) return "var(--yellow)";
  return "var(--red)";
}

export function LiveStatus({ last, allowed, blocked }: Props) {
  const limit = last?.limit ?? 0;
  const rem = last?.remaining ?? 0;
  const pct = limit > 0 ? Math.max(0, Math.min(100, (rem / limit) * 100)) : 100;

  const rows: [string, string | number | null][] = last
    ? [
        ["x-ratelimit-limit", last.limit || null],
        ["x-ratelimit-remaining", last.remaining],
        ["x-ratelimit-reset", last.reset],
        ["x-ratelimit-policy", last.policy || null],
        ["retry-after", last.retry],
      ]
    : [];

  return (
    <div className="panel">
      <h2>Live Status</h2>

      <div className="quota-wrap">
        <div className="quota-labels">
          <span>Remaining quota</span>
          <span>{limit > 0 ? `${rem} / ${limit}` : "— / —"}</span>
        </div>
        <div className="quota-bar">
          <div
            className="quota-fill"
            style={{ width: `${pct}%`, background: quotaColor(pct) }}
          />
        </div>
      </div>

      <div className="stats">
        <div className="stat allowed">
          <div className="num">{allowed}</div>
          <div className="lbl">Allowed</div>
        </div>
        <div className="stat blocked">
          <div className="num">{blocked}</div>
          <div className="lbl">Blocked</div>
        </div>
        <div className="stat">
          <div className="num">{allowed + blocked}</div>
          <div className="lbl">Total</div>
        </div>
      </div>

      <h2 style={{ marginTop: 6 }}>Response Headers</h2>
      <div className="headers">
        {rows.length === 0 ? (
          <div className="empty">Send a request to see rate-limit headers</div>
        ) : (
          rows
            .filter(([, v]) => v !== null && v !== undefined)
            .map(([k, v]) => (
              <div className="row" key={k}>
                <span className="k">{k}</span>
                <span className="v">{v}</span>
              </div>
            ))
        )}
      </div>
    </div>
  );
}
