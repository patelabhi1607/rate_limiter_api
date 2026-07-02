import type { LogEntry } from "../types";

export function RequestLog({ entries }: { entries: LogEntry[] }) {
  return (
    <div className="panel" style={{ marginTop: 20 }}>
      <h2>Request Log</h2>
      <div className="log">
        {entries.length === 0 ? (
          <div className="empty">No requests yet</div>
        ) : (
          entries.map((e) => (
            <div
              key={e.id}
              className={"log-item " + (e.status === 200 ? "ok" : "blocked")}
            >
              <span className="code">{e.status}</span>
              <span className="path">
                {e.time} · {e.path}
              </span>
              <span className="rem">
                {e.remaining !== null ? `rem ${e.remaining}` : ""}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
