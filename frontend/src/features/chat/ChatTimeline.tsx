import styles from "./ChatTimeline.module.css";
import type { TimelineEntry } from "../../app/store";

interface ChatTimelineProps {
  entries: TimelineEntry[];
  onRetryMessage: (entryId: string) => Promise<void> | void;
  onRecommendationFeedback: (
    recommendationId: string,
    nodeId: string | null,
    action: "accepted" | "snoozed" | "dismissed",
  ) => Promise<void> | void;
}

export function ChatTimeline({ entries, onRetryMessage, onRecommendationFeedback }: ChatTimelineProps) {
  return (
    <div className={styles.shell}>
      <div className={styles.header}>
        <h2 className={styles.title}>Timeline</h2>
        <div className={styles.hint}>This stays local to the current page session and does not restore chat history.</div>
      </div>

      {entries.length === 0 ? (
        <div className={styles.empty}>
          No conversation yet. Send one short update, or start with <code>/pull</code> / <code>/brief</code>.
        </div>
      ) : null}

      {entries.map((entry) => {
        if (entry.kind === "user") {
          return (
            <article key={entry.id} className={`${styles.entry} ${styles.user}`}>
              <div className={styles.entryMeta}>
                <span>You</span>
                <span className={styles.status}>{entry.status}</span>
              </div>
              <p className={styles.entryText}>{entry.text}</p>
              {entry.errorMessage ? <div className={styles.error}>{entry.errorMessage}</div> : null}
              {entry.status === "failed" ? (
                <button className={styles.retryButton} type="button" onClick={() => void onRetryMessage(entry.id)}>
                  Retry
                </button>
              ) : null}
            </article>
          );
        }

        if (entry.kind === "assistant") {
          return (
            <article key={entry.id} className={`${styles.entry} ${styles.assistant}`}>
              <div className={styles.entryMeta}>
                <span>Assistant ACK</span>
                <span>event_id: {entry.eventId ?? "--"}</span>
              </div>
              <p className={styles.entryText}>{entry.text}</p>
            </article>
          );
        }

        if (entry.kind === "system") {
          return (
            <article
              key={entry.id}
              className={`${styles.entry} ${entry.tone === "error" ? styles.systemError : styles.systemInfo}`}
            >
              <div className={styles.entryMeta}>
                <span>System notice</span>
              </div>
              <p className={styles.entryText}>{entry.text}</p>
            </article>
          );
        }

        return (
          <article key={entry.id} className={`${styles.entry} ${styles.recommendationCard}`}>
            <div className={styles.entryMeta}>
              <span>Recommendation</span>
              <span className={styles.status}>{entry.status}</span>
            </div>

            {entry.status === "load_failed" ? (
              <div className={styles.errorBlock}>
                Recommendation pull failed: {entry.errorMessage ?? "Please try again from the sidebar."}
              </div>
            ) : entry.emptyState ? (
              <>
                <div className={styles.fallback}>{entry.fallbackMessage ?? "No strong candidate right now."}</div>
                <div className={styles.quickChips}>
                  <span className={styles.quickChip}>Within 10 min</span>
                  <span className={styles.quickChip}>Low mental load</span>
                  <span className={styles.quickChip}>Indoor</span>
                </div>
              </>
            ) : (
              <div className={styles.recommendationList}>
                {entry.items.map((item) => (
                  <div key={item.node_id} className={styles.recommendationItem}>
                    <strong>{item.title}</strong>
                    <p className={styles.entryText}>{item.message}</p>
                    <div className={styles.tags}>
                      {item.reason_tags.map((tag) => (
                        <span key={tag} className={styles.tag}>
                          {tag}
                        </span>
                      ))}
                    </div>
                    <div className={styles.actions}>
                      <button
                        className={styles.feedbackButton}
                        type="button"
                        disabled={entry.status === "feedback_submitting"}
                        onClick={() => void onRecommendationFeedback(entry.recommendationId, item.node_id, "accepted")}
                      >
                        Accept
                      </button>
                      <button
                        className={styles.secondaryFeedbackButton}
                        type="button"
                        disabled={entry.status === "feedback_submitting"}
                        onClick={() => void onRecommendationFeedback(entry.recommendationId, item.node_id, "snoozed")}
                      >
                        Snooze
                      </button>
                      <button
                        className={styles.secondaryFeedbackButton}
                        type="button"
                        disabled={entry.status === "feedback_submitting"}
                        onClick={() => void onRecommendationFeedback(entry.recommendationId, item.node_id, "dismissed")}
                      >
                        Swap
                      </button>
                    </div>
                    {entry.status === "feedback_failed" ? (
                      <div className={styles.error}>Feedback could not be recorded. Try again.</div>
                    ) : null}
                  </div>
                ))}
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
}
