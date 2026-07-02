import { useCallback, useEffect, useRef, useState } from "react";
import { Controls } from "./components/Controls";
import { LiveStatus } from "./components/LiveStatus";
import { RequestLog } from "./components/RequestLog";
import { API_URL, callApi, checkBackend } from "./api";
import { simulate } from "./simulator";
import { ENDPOINTS } from "./endpoints";
import type { LogEntry, RateLimitResult } from "./types";

type Mode = "checking" | "live" | "sim";

export function App() {
  const [endpoint, setEndpoint] = useState(ENDPOINTS[0].path);
  const [burst, setBurst] = useState(15);
  const [mode, setMode] = useState<Mode>("checking");
  const [allowed, setAllowed] = useState(0);
  const [blocked, setBlocked] = useState(0);
  const [last, setLast] = useState<RateLimitResult | null>(null);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [busy, setBusy] = useState(false);

  // `mode` is also read inside async loops; keep a ref in sync to avoid stale reads.
  const modeRef = useRef<Mode>("checking");
  const logId = useRef(0);
  useEffect(() => {
    modeRef.current = mode;
  }, [mode]);

  useEffect(() => {
    checkBackend().then((ok) => setMode(ok ? "live" : "sim"));
  }, []);

  const record = useCallback((res: RateLimitResult, path: string) => {
    setLast(res);
    if (res.status === 200) setAllowed((n) => n + 1);
    else if (res.status === 429) setBlocked((n) => n + 1);
    setLog((prev) => {
      const entry: LogEntry = {
        id: logId.current++,
        status: res.status,
        path,
        remaining: res.remaining,
        time: new Date().toLocaleTimeString(),
      };
      return [entry, ...prev].slice(0, 50);
    });
  }, []);

  const fire = useCallback(
    async (path: string) => {
      if (modeRef.current === "live") {
        try {
          const res = await callApi(path);
          record(res, path);
          return;
        } catch {
          // backend went away → drop to simulated mode
          setMode("sim");
          modeRef.current = "sim";
        }
      }
      record(simulate(path), path);
    },
    [record],
  );

  const sendOne = useCallback(() => fire(endpoint), [fire, endpoint]);

  const sendBurst = useCallback(async () => {
    const n = Math.max(1, Math.min(200, burst));
    setBusy(true);
    await Promise.all(Array.from({ length: n }, () => fire(endpoint)));
    setBusy(false);
  }, [burst, endpoint, fire]);

  const reset = useCallback(() => {
    setAllowed(0);
    setBlocked(0);
    setLast(null);
    setLog([]);
  }, []);

  return (
    <div className="wrap">
      <h1>
        Rate Limiter <span className="tag">API</span>
      </h1>
      <p className="subtitle">
        Interactive demo — fire requests and watch the limiter allow or block
        them in real time.
      </p>
      <div className={"badge " + (mode === "live" ? "live" : mode === "sim" ? "sim" : "")}>
        {mode === "checking" && "Checking backend…"}
        {mode === "live" && "● Live backend connected"}
        {mode === "sim" &&
          "● Simulated mode (no backend) — same algorithms, in your browser"}
      </div>

      <div className="grid">
        <Controls
          endpoint={endpoint}
          onEndpointChange={setEndpoint}
          burst={burst}
          onBurstChange={setBurst}
          onSendOne={sendOne}
          onSendBurst={sendBurst}
          onReset={reset}
          busy={busy}
        />
        <LiveStatus last={last} allowed={allowed} blocked={blocked} />
      </div>

      <RequestLog entries={log} />

      <div className="footer">
        Rate Limiter API · FastAPI + Redis + PostgreSQL ·{" "}
        <a href={API_URL + "/docs"} target="_blank" rel="noreferrer">
          API Docs
        </a>{" "}
        ·{" "}
        <a href={API_URL + "/metrics"} target="_blank" rel="noreferrer">
          Metrics
        </a>
      </div>
    </div>
  );
}
