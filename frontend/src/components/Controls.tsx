import { ENDPOINTS, findEndpoint } from "../endpoints";

interface Props {
  endpoint: string;
  onEndpointChange: (path: string) => void;
  burst: number;
  onBurstChange: (n: number) => void;
  onSendOne: () => void;
  onSendBurst: () => void;
  onReset: () => void;
  busy: boolean;
}

export function Controls({
  endpoint,
  onEndpointChange,
  burst,
  onBurstChange,
  onSendOne,
  onSendBurst,
  onReset,
  busy,
}: Props) {
  const cfg = findEndpoint(endpoint);
  return (
    <div className="panel">
      <h2>Send Requests</h2>

      <label htmlFor="endpoint">Demo Endpoint</label>
      <select
        id="endpoint"
        value={endpoint}
        onChange={(e) => onEndpointChange(e.target.value)}
      >
        {ENDPOINTS.map((e) => (
          <option key={e.path} value={e.path}>
            {e.label}
          </option>
        ))}
      </select>
      <div className="endpoint-desc">{cfg.desc}</div>

      <label htmlFor="burst">Burst size</label>
      <input
        id="burst"
        type="number"
        min={1}
        max={200}
        value={burst}
        onChange={(e) => onBurstChange(parseInt(e.target.value, 10) || 1)}
      />

      <div className="btn-row">
        <button onClick={onSendOne} disabled={busy}>
          Send 1 Request
        </button>
        <button className="secondary" onClick={onSendBurst} disabled={busy}>
          Send Burst
        </button>
      </div>
      <div className="btn-row" style={{ marginTop: 10 }}>
        <button className="secondary" onClick={onReset} disabled={busy}>
          Reset Stats
        </button>
      </div>
    </div>
  );
}
