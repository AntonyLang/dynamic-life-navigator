import { useState } from "react";

import type { DebugEvent } from "../../app/store";
import type { ActionNodeCreateRequest, StateResetRequest } from "../../lib/api/types";
import { maybeNumber, parseTags } from "../../lib/forms";
import styles from "./DevPanel.module.css";

interface DevPanelProps {
  open: boolean;
  onToggle: () => void;
  onResetState: (payload: StateResetRequest) => Promise<void> | void;
  onCreateNode: (payload: ActionNodeCreateRequest) => Promise<void> | void;
  lastDebugEvent: DebugEvent | null;
  debugEvents: DebugEvent[];
  busy: boolean;
}

export function DevPanel({
  open,
  onToggle,
  onResetState,
  onCreateNode,
  lastDebugEvent,
  debugEvents,
  busy,
}: DevPanelProps) {
  const [mentalEnergy, setMentalEnergy] = useState("55");
  const [physicalEnergy, setPhysicalEnergy] = useState("45");
  const [reason, setReason] = useState("frontend manual reset");

  const [driveType, setDriveType] = useState<ActionNodeCreateRequest["drive_type"]>("project");
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [tags, setTags] = useState("");
  const [priorityScore, setPriorityScore] = useState("");
  const [urgencyScore, setUrgencyScore] = useState("");
  const [estimatedMinutes, setEstimatedMinutes] = useState("");
  const [ddlTimestamp, setDdlTimestamp] = useState("");

  async function submitReset() {
    await onResetState({
      mental_energy: Number(mentalEnergy),
      physical_energy: Number(physicalEnergy),
      reason,
    });
  }

  async function submitNode() {
    await onCreateNode({
      drive_type: driveType,
      title,
      summary: summary || null,
      tags: parseTags(tags),
      priority_score: maybeNumber(priorityScore),
      dynamic_urgency_score: maybeNumber(urgencyScore),
      estimated_minutes: maybeNumber(estimatedMinutes),
      ddl_timestamp: ddlTimestamp ? new Date(ddlTimestamp).toISOString() : null,
    });
  }

  return (
    <section className={styles.card}>
      <div className={styles.header}>
        <h2 className={styles.title}>Dev Panel</h2>
        <button className={styles.button} type="button" onClick={onToggle}>
          {open ? "Collapse" : "Expand"}
        </button>
      </div>

      {!open ? <div className={styles.placeholder}>Expand to reset state or create an action node.</div> : null}

      {open ? (
        <div className={styles.stack}>
          <section className={styles.section}>
            <h3 className={styles.sectionTitle}>State Reset</h3>
            <div className={styles.form}>
              <div className={styles.row}>
                <label className={styles.field}>
                  <span>Mental energy</span>
                  <input value={mentalEnergy} onChange={(event) => setMentalEnergy(event.target.value)} />
                </label>
                <label className={styles.field}>
                  <span>Physical energy</span>
                  <input value={physicalEnergy} onChange={(event) => setPhysicalEnergy(event.target.value)} />
                </label>
              </div>
              <label className={styles.field}>
                <span>Reason</span>
                <input value={reason} onChange={(event) => setReason(event.target.value)} />
              </label>
              <button className={styles.submit} type="button" onClick={() => void submitReset()} disabled={busy}>
                Submit reset
              </button>
            </div>
          </section>

          <section className={styles.section}>
            <h3 className={styles.sectionTitle}>Create Node</h3>
            <div className={styles.form}>
              <div className={styles.row}>
                <label className={styles.field}>
                  <span>Drive type</span>
                  <select
                    value={driveType}
                    onChange={(event) => setDriveType(event.target.value as ActionNodeCreateRequest["drive_type"])}
                  >
                    <option value="project">project</option>
                    <option value="value">value</option>
                  </select>
                </label>
                <label className={styles.field}>
                  <span>Title</span>
                  <input value={title} onChange={(event) => setTitle(event.target.value)} />
                </label>
              </div>
              <label className={styles.field}>
                <span>Summary</span>
                <textarea value={summary} onChange={(event) => setSummary(event.target.value)} />
              </label>
              <label className={styles.field}>
                <span>Tags</span>
                <input value={tags} onChange={(event) => setTags(event.target.value)} placeholder="coding, urgent, indoor" />
              </label>
              <div className={styles.row}>
                <label className={styles.field}>
                  <span>Priority score</span>
                  <input value={priorityScore} onChange={(event) => setPriorityScore(event.target.value)} />
                </label>
                <label className={styles.field}>
                  <span>Dynamic urgency</span>
                  <input value={urgencyScore} onChange={(event) => setUrgencyScore(event.target.value)} />
                </label>
              </div>
              <div className={styles.row}>
                <label className={styles.field}>
                  <span>Estimated minutes</span>
                  <input value={estimatedMinutes} onChange={(event) => setEstimatedMinutes(event.target.value)} />
                </label>
                <label className={styles.field}>
                  <span>DDL timestamp</span>
                  <input type="datetime-local" value={ddlTimestamp} onChange={(event) => setDdlTimestamp(event.target.value)} />
                </label>
              </div>
              <button className={styles.submit} type="button" onClick={() => void submitNode()} disabled={busy}>
                Create node
              </button>
            </div>
          </section>

          <section className={styles.section}>
            <h3 className={styles.sectionTitle}>Latest Debug Event</h3>
            {lastDebugEvent ? (
              <div className={styles.debug}>
                <div>
                  label: <code>{lastDebugEvent.label}</code>
                </div>
                <div>
                  request_id: <code>{lastDebugEvent.requestId ?? "--"}</code>
                </div>
                <div>
                  recommendation_id: <code>{lastDebugEvent.recommendationId ?? "--"}</code>
                </div>
                <div>
                  event_id: <code>{lastDebugEvent.eventId ?? "--"}</code>
                </div>
                <pre>{JSON.stringify(lastDebugEvent.response, null, 2)}</pre>
              </div>
            ) : (
              <div className={styles.placeholder}>No debug event yet.</div>
            )}

            {debugEvents.length > 0 ? (
              <div className={styles.history}>
                <h4 className={styles.historyTitle}>Recent events</h4>
                <ul className={styles.historyList}>
                  {debugEvents.map((event) => (
                    <li key={`${event.createdAt}-${event.label}`} className={styles.historyItem}>
                      <code>{event.label}</code>
                      <span>{new Date(event.createdAt).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </section>
        </div>
      ) : null}
    </section>
  );
}
