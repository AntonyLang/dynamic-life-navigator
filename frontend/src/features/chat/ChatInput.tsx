import { FormEvent } from "react";

import styles from "./ChatInput.module.css";

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: (value: string) => Promise<void> | void;
  onPull: () => Promise<void> | void;
  onBrief: () => Promise<void> | void;
  onQuickFill: (value: string) => void;
  disabled?: boolean;
}

export function ChatInput({ value, onChange, onSend, onPull, onBrief, onQuickFill, disabled = false }: ChatInputProps) {
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = value.trim();
    if (!text) {
      return;
    }
    await onSend(text);
  }

  return (
    <form className={styles.shell} onSubmit={(event) => void handleSubmit(event)}>
      <div className={styles.topline}>
        <div>
          <h2 className={styles.title}>Input</h2>
          <div className={styles.hint}>Supports plain text, `/pull`, and `/brief`.</div>
        </div>
        <div className={styles.quickRow}>
          <button className={styles.chip} type="button" onClick={() => onQuickFill("/pull")}>
            /pull
          </button>
          <button className={styles.chip} type="button" onClick={() => onQuickFill("/brief")}>
            /brief
          </button>
        </div>
      </div>

      <label>
        <span className={styles.hint}>Send the backend a short update, context change, or a direct request.</span>
        <textarea
          className={styles.textarea}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="For example: I just finished a heavy debugging session and my brain feels empty."
          disabled={disabled}
        />
      </label>

      <div className={styles.footer}>
        <button className={styles.primaryButton} type="submit" disabled={disabled}>
          Send
        </button>
        <button className={styles.ghostButton} type="button" onClick={() => void onPull()} disabled={disabled}>
          Pull recommendation
        </button>
        <button className={styles.ghostButton} type="button" onClick={() => void onBrief()} disabled={disabled}>
          Open brief
        </button>
      </div>
    </form>
  );
}
