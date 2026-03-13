import styles from "./RecommendationSidebar.module.css";
import type { RecommendationPullResponse } from "../../lib/api/types";

interface RecommendationSidebarProps {
  recommendation: RecommendationPullResponse | null;
  loading: boolean;
  onPull: () => Promise<void> | void;
  onPrefill: (value: string) => void;
}

const quickPrefills = [
  { label: "Within 10 min", value: "Only show things I can finish within 10 minutes." },
  { label: "Low mental load", value: "Only show things that do not require much mental energy." },
  { label: "Indoor", value: "Only show things I can do indoors." },
];

export function RecommendationSidebar({ recommendation, loading, onPull, onPrefill }: RecommendationSidebarProps) {
  return (
    <section className={styles.card}>
      <div className={styles.topline}>
        <div>
          <h2 className={styles.title}>Recommendation Sidebar</h2>
          <div className={styles.hint}>Keep the latest recommendation_id visible for feedback wiring.</div>
        </div>
        <button className={styles.button} type="button" onClick={() => void onPull()} disabled={loading}>
          {loading ? "Loading" : "Pull"}
        </button>
      </div>

      {!recommendation ? <div className={styles.placeholder}>No recommendation has been pulled yet.</div> : null}

      {recommendation?.empty_state ? (
        <div className={styles.fallback}>
          <div>{recommendation.fallback_message ?? "No strong candidate right now."}</div>
          <div className={styles.quickRow}>
            {quickPrefills.map((item) => (
              <button key={item.label} className={styles.quickButton} type="button" onClick={() => onPrefill(item.value)}>
                {item.label}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {recommendation && !recommendation.empty_state
        ? recommendation.items.map((item) => (
            <article key={item.node_id} className={styles.item}>
              <h3 className={styles.itemTitle}>{item.title}</h3>
              <p>{item.message}</p>
              <div className={styles.tags}>
                {item.reason_tags.map((tag) => (
                  <span key={tag} className={styles.tag}>
                    {tag}
                  </span>
                ))}
              </div>
            </article>
          ))
        : null}
    </section>
  );
}
