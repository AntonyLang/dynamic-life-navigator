import type { BridgeConfig, PingBackendResult } from "../types";

interface SettingsDrawerProps {
  open: boolean;
  configDraft: BridgeConfig;
  pingResult: PingBackendResult | null;
  statusMessage: string | null;
  saving: boolean;
  pinging: boolean;
  onClose: () => void;
  onChange: (field: keyof BridgeConfig, value: string) => void;
  onSave: () => Promise<void> | void;
  onPing: () => Promise<void> | void;
}

export function SettingsDrawer({
  open,
  configDraft,
  pingResult,
  statusMessage,
  saving,
  pinging,
  onClose,
  onChange,
  onSave,
  onPing,
}: SettingsDrawerProps) {
  if (!open) {
    return null;
  }

  return (
    <div className="drawer-backdrop" role="dialog" aria-modal="true">
      <aside className="drawer drawer-narrow">
        <div className="panel-header">
          <div>
            <h2 className="panel-title panel-title-small">Connection Settings</h2>
            <p className="panel-subtitle">Renderer traffic goes through preload and uses this backend origin.</p>
          </div>
          <button className="ghost-button" type="button" onClick={onClose}>
            Close
          </button>
        </div>

        <label className="field-label">
          <span>Server origin</span>
          <input
            className="text-input"
            value={configDraft.serverOrigin}
            onChange={(event) => onChange("serverOrigin", event.target.value)}
            placeholder="http://127.0.0.1:8000"
          />
        </label>

        <label className="field-label">
          <span>Auth token</span>
          <input
            className="text-input"
            value={configDraft.authToken ?? ""}
            onChange={(event) => onChange("authToken", event.target.value)}
            placeholder="Optional bearer token"
          />
        </label>

        <div className="action-row">
          <button className="primary-button" type="button" onClick={() => void onSave()} disabled={saving}>
            {saving ? "Saving" : "Save"}
          </button>
          <button className="ghost-button" type="button" onClick={() => void onPing()} disabled={pinging}>
            {pinging ? "Pinging" : "Ping backend"}
          </button>
        </div>

        {statusMessage ? <div className="inline-note">{statusMessage}</div> : null}
        {pingResult ? (
          <div className="inline-note">
            Ping OK: {pingResult.status} / {pingResult.responseTimeMs}ms
          </div>
        ) : null}
      </aside>
    </div>
  );
}
