import type { UserStateSnapshot } from "../types";
import { formatDateTime, isStateStale } from "../utils";

interface StatePanelProps {
  state: UserStateSnapshot | null;
  loading: boolean;
  connectionStatus: "checking" | "connected" | "disconnected";
  errorMessage: string | null;
  lastSuccessfulAt: number | null;
  onOpenSettings: () => void;
}

export function StatePanel({
  state,
  loading,
  connectionStatus,
  errorMessage,
  lastSuccessfulAt,
  onOpenSettings,
}: StatePanelProps) {
  const stale = isStateStale(lastSuccessfulAt, Date.now());
  const stateLabel = loading ? "loading" : errorMessage ? "error" : stale ? "stale" : "ready";
  const connectionLabel =
    connectionStatus === "checking" ? "Checking" : connectionStatus === "connected" ? "Connected" : "Disconnected";

  return (
    <section className="panel state-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Dynamic Life Navigator</p>
          <h1 className="panel-title">uTools Shell</h1>
        </div>
        <div className="header-actions">
          <span className={`status-pill ${loading ? "loading" : errorMessage ? "error" : stale ? "stale" : "ok"}`}>
            {stateLabel}
          </span>
          <button className="ghost-button" type="button" onClick={onOpenSettings}>
            Settings
          </button>
        </div>
      </div>

      <div className="state-meta-row">
        <span>Connection: {connectionLabel}</span>
        <span>Last update: {formatDateTime(state?.last_updated_at)}</span>
      </div>

      <div className="state-grid">
        <div className="metric-card">
          <span className="metric-label">Mental Energy</span>
          <strong>{state?.mental_energy ?? "--"}</strong>
        </div>
        <div className="metric-card">
          <span className="metric-label">Physical Energy</span>
          <strong>{state?.physical_energy ?? "--"}</strong>
        </div>
        <div className="metric-card">
          <span className="metric-label">Focus Mode</span>
          <strong>{state?.focus_mode ?? "--"}</strong>
        </div>
        <div className="metric-card">
          <span className="metric-label">Recent Context</span>
          <strong className="context-value">{state?.recent_context ?? "No recent context"}</strong>
        </div>
      </div>

      {errorMessage ? <div className="inline-error">State request failed: {errorMessage}</div> : null}
      {!errorMessage && stale ? <div className="inline-note">State refresh is older than 60 seconds.</div> : null}
    </section>
  );
}
