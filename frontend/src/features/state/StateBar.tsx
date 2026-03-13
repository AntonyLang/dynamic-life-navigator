import styles from "./StateBar.module.css";
import type { UserStateSnapshot } from "../../lib/api/types";
import { formatDateTime } from "../../lib/time";

interface StateBarProps {
  state: UserStateSnapshot | null;
  stale: boolean;
  loading: boolean;
  errorMessage: string | null;
}

export function StateBar({ state, stale, loading, errorMessage }: StateBarProps) {
  const statusLabel = loading ? "loading" : stale ? "stale" : "healthy";
  const statusClassName = `${styles.status} ${loading ? styles.statusLoading : stale ? styles.statusStale : ""}`.trim();

  return (
    <section className={styles.card}>
      <div className={styles.topline}>
        <div>
          <p className={styles.eyebrow}>State Snapshot</p>
          <h2 className={styles.title}>Current state follows /api/v1/state.</h2>
        </div>
        <div className={statusClassName}>{statusLabel}</div>
      </div>

      <p className={styles.meta}>Recent context: {state?.recent_context ?? "No recent context."}</p>

      <div className={styles.grid}>
        <div className={styles.metric}>
          <span className={styles.metricLabel}>Mental energy</span>
          <span className={styles.metricValue}>{state?.mental_energy ?? "--"}</span>
        </div>
        <div className={styles.metric}>
          <span className={styles.metricLabel}>Physical energy</span>
          <span className={styles.metricValue}>{state?.physical_energy ?? "--"}</span>
        </div>
        <div className={styles.metric}>
          <span className={styles.metricLabel}>Focus mode</span>
          <span className={styles.metricValue}>{state?.focus_mode ?? "--"}</span>
        </div>
        <div className={styles.metric}>
          <span className={styles.metricLabel}>Last updated</span>
          <span className={styles.metricValue}>{formatDateTime(state?.last_updated_at)}</span>
        </div>
      </div>

      {stale && errorMessage ? <div className={styles.hint}>State request failed: {errorMessage}</div> : null}
    </section>
  );
}
