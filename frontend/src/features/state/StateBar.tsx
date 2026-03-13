import { useEffect, useState } from "react";

import { STATE_STALE_THRESHOLD_MS } from "../../app/hooks/flowUtils";
import type { UserStateSnapshot } from "../../lib/api/types";
import { formatDateTime } from "../../lib/time";
import styles from "./StateBar.module.css";

interface StateBarProps {
  state: UserStateSnapshot | null;
  stale: boolean;
  loading: boolean;
  errorMessage: string | null;
  lastSuccessfulAt: number | null;
}

export function StateBar({ state, stale, loading, errorMessage, lastSuccessfulAt }: StateBarProps) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 15_000);
    return () => window.clearInterval(timer);
  }, []);

  const staleByAge = lastSuccessfulAt !== null && now - lastSuccessfulAt > STATE_STALE_THRESHOLD_MS;
  const isStale = stale || staleByAge;
  const statusLabel = loading ? "loading" : isStale ? "stale" : "healthy";
  const statusClassName = `${styles.status} ${loading ? styles.statusLoading : isStale ? styles.statusStale : ""}`.trim();

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
      {!stale && staleByAge ? <div className={styles.hint}>Latest successful state refresh is older than 60 seconds.</div> : null}
    </section>
  );
}
