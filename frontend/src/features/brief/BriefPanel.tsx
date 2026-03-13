import styles from "./BriefPanel.module.css";
import type { RecommendationBriefResponse } from "../../lib/api/types";

interface BriefPanelProps {
  brief: RecommendationBriefResponse | null;
  loading: boolean;
  open: boolean;
  onToggle: () => void;
  onRefresh: () => Promise<void> | void;
}

export function BriefPanel({ brief, loading, open, onToggle, onRefresh }: BriefPanelProps) {
  return (
    <section className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>Brief</h2>
        <div className={styles.controls}>
          <button className={styles.button} type="button" onClick={onToggle}>
            {open ? "Collapse" : "Expand"}
          </button>
          <button className={styles.button} type="button" onClick={() => void onRefresh()} disabled={loading}>
            {loading ? "Refreshing" : "Refresh"}
          </button>
        </div>
      </div>

      {!open ? <div className={styles.placeholder}>Panel is collapsed. Expand it to load /brief.</div> : null}
      {open && !brief ? <div className={styles.placeholder}>Brief data is not loaded yet.</div> : null}

      {open && brief ? (
        <>
          <div className={styles.summaryGrid}>
            <div className={styles.summaryItem}>
              <span className={styles.summaryLabel}>Active projects</span>
              <span className={styles.summaryValue}>{brief.summary.active_projects}</span>
            </div>
            <div className={styles.summaryItem}>
              <span className={styles.summaryLabel}>Active values</span>
              <span className={styles.summaryValue}>{brief.summary.active_values}</span>
            </div>
            <div className={styles.summaryItem}>
              <span className={styles.summaryLabel}>Urgent nodes</span>
              <span className={styles.summaryValue}>{brief.summary.urgent_nodes}</span>
            </div>
            <div className={styles.summaryItem}>
              <span className={styles.summaryLabel}>Stale nodes</span>
              <span className={styles.summaryValue}>{brief.summary.stale_nodes}</span>
            </div>
          </div>

          <div className={styles.list}>
            {brief.items.map((item) => (
              <article key={item.node_id} className={styles.item}>
                <strong>{item.title}</strong>
                <div className={styles.itemMeta}>
                  {item.status} / {item.health}
                </div>
                <p>{item.next_hint}</p>
              </article>
            ))}
          </div>
        </>
      ) : null}
    </section>
  );
}
