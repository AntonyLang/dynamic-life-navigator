import type { RecommendationFeedbackType, TimelineEntry } from "../types";

interface TimelineProps {
  entries: TimelineEntry[];
  onRetryMessage: (entryId: string) => Promise<void> | void;
  onRecommendationFeedback: (
    recommendationId: string,
    nodeId: string | null,
    feedback: RecommendationFeedbackType,
  ) => Promise<void> | void;
}

export function Timeline({ entries, onRetryMessage, onRecommendationFeedback }: TimelineProps) {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2 className="panel-title panel-title-small">Timeline</h2>
          <p className="panel-subtitle">Local session timeline for chat ack, system prompts, and recommendation cards.</p>
        </div>
      </div>

      {entries.length === 0 ? (
        <div className="empty-state">还没有交互。输入一条更新，或者直接使用 /pull /brief。</div>
      ) : null}

      <div className="timeline-list">
        {entries.map((entry) => {
          if (entry.kind === "user") {
            return (
              <article key={entry.id} className="timeline-card timeline-user">
                <div className="timeline-meta">
                  <span>You</span>
                  <span>{entry.status}</span>
                </div>
                <p>{entry.text}</p>
                {entry.errorMessage ? <div className="inline-error">{entry.errorMessage}</div> : null}
                {entry.status === "failed" ? (
                  <button className="ghost-button" type="button" onClick={() => void onRetryMessage(entry.id)}>
                    Retry
                  </button>
                ) : null}
              </article>
            );
          }

          if (entry.kind === "assistant") {
            return (
              <article key={entry.id} className="timeline-card timeline-assistant">
                <div className="timeline-meta">
                  <span>Assistant ACK</span>
                  <span>{entry.eventId ? `event_id: ${entry.eventId}` : "event_id: --"}</span>
                </div>
                <p>{entry.text}</p>
              </article>
            );
          }

          if (entry.kind === "system") {
            return (
              <article key={entry.id} className={`timeline-card ${entry.tone === "error" ? "timeline-error" : "timeline-system"}`}>
                <div className="timeline-meta">
                  <span>System</span>
                </div>
                <p>{entry.text}</p>
              </article>
            );
          }

          return (
            <article key={entry.id} className="timeline-card timeline-recommendation">
              <div className="timeline-meta">
                <span>Recommendation</span>
                <span>{entry.status}</span>
              </div>

              {entry.status === "load_failed" ? (
                <div className="inline-error">
                  Recommendation pull failed: {entry.errorMessage ?? "Please try again."}
                </div>
              ) : entry.emptyState ? (
                <div className="fallback-block">
                  <p>{entry.fallbackMessage ?? "No strong candidate right now."}</p>
                  <div className="chip-row">
                    <span className="chip">Within 10 min</span>
                    <span className="chip">Low mental load</span>
                    <span className="chip">Indoor</span>
                  </div>
                </div>
              ) : (
                <div className="recommendation-list">
                  {entry.items.map((item) => (
                    <div key={item.node_id} className="recommendation-item">
                      <strong>{item.title}</strong>
                      <p>{item.message}</p>
                      <div className="tag-row">
                        {item.reason_tags.map((tag) => (
                          <span key={tag} className="tag">
                            {tag}
                          </span>
                        ))}
                      </div>
                      <div className="action-row">
                        <button
                          className="primary-button"
                          type="button"
                          disabled={entry.status === "feedback_submitting"}
                          onClick={() => void onRecommendationFeedback(entry.recommendationId, item.node_id, "accepted")}
                        >
                          Accept
                        </button>
                        <button
                          className="ghost-button"
                          type="button"
                          disabled={entry.status === "feedback_submitting"}
                          onClick={() => void onRecommendationFeedback(entry.recommendationId, item.node_id, "snoozed")}
                        >
                          Snooze
                        </button>
                        <button
                          className="ghost-button"
                          type="button"
                          disabled={entry.status === "feedback_submitting"}
                          onClick={() => void onRecommendationFeedback(entry.recommendationId, item.node_id, "dismissed")}
                        >
                          Swap
                        </button>
                      </div>
                      {entry.status === "feedback_failed" ? (
                        <div className="inline-error">{entry.errorMessage ?? "Feedback failed."}</div>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
