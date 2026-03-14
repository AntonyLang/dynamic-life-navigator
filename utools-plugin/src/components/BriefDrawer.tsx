import type { RecommendationBriefResponse } from "../types";

interface BriefDrawerProps {
  open: boolean;
  loading: boolean;
  brief: RecommendationBriefResponse | null;
  onClose: () => void;
  onRefresh: () => Promise<void> | void;
}

export function BriefDrawer({ open, loading, brief, onClose, onRefresh }: BriefDrawerProps) {
  if (!open) {
    return null;
  }

  return (
    <div className="drawer-backdrop" role="dialog" aria-modal="true">
      <aside className="drawer">
        <div className="panel-header">
          <div>
            <h2 className="panel-title panel-title-small">Brief</h2>
            <p className="panel-subtitle">Current brief summary from /api/v1/brief.</p>
          </div>
          <div className="header-actions">
            <button className="ghost-button" type="button" onClick={() => void onRefresh()} disabled={loading}>
              {loading ? "Refreshing" : "Refresh"}
            </button>
            <button className="ghost-button" type="button" onClick={onClose}>
              Close
            </button>
          </div>
        </div>

        {!brief ? <div className="empty-state">Brief data is not loaded yet.</div> : null}

        {brief ? (
          <>
            <div className="state-grid">
              <div className="metric-card">
                <span className="metric-label">Active projects</span>
                <strong>{brief.summary.active_projects}</strong>
              </div>
              <div className="metric-card">
                <span className="metric-label">Active values</span>
                <strong>{brief.summary.active_values}</strong>
              </div>
              <div className="metric-card">
                <span className="metric-label">Urgent nodes</span>
                <strong>{brief.summary.urgent_nodes}</strong>
              </div>
              <div className="metric-card">
                <span className="metric-label">Stale nodes</span>
                <strong>{brief.summary.stale_nodes}</strong>
              </div>
            </div>

            <div className="brief-list">
              {brief.items.map((item) => (
                <article key={item.node_id} className="brief-item">
                  <strong>{item.title}</strong>
                  <div className="brief-meta">
                    {item.status} / {item.health}
                  </div>
                  <p>{item.next_hint}</p>
                </article>
              ))}
            </div>
          </>
        ) : null}
      </aside>
    </div>
  );
}
