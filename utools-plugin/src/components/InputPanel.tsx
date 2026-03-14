interface InputPanelProps {
  value: string;
  disabled?: boolean;
  onChange: (value: string) => void;
  onSend: (text: string) => Promise<void> | void;
  onPull: () => Promise<void> | void;
  onBrief: () => Promise<void> | void;
  onQuickFill: (value: string) => void;
}

export function InputPanel({
  value,
  disabled = false,
  onChange,
  onSend,
  onPull,
  onBrief,
  onQuickFill,
}: InputPanelProps) {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2 className="panel-title panel-title-small">Input</h2>
          <p className="panel-subtitle">Supports normal text, /pull, and /brief.</p>
        </div>
        <div className="chip-row">
          <button className="chip-button" type="button" onClick={() => onQuickFill("/pull")}>
            /pull
          </button>
          <button className="chip-button" type="button" onClick={() => onQuickFill("/brief")}>
            /brief
          </button>
        </div>
      </div>

      <textarea
        className="message-input"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="For example: 刚做完很重的脑力活，想先缓一下。"
        disabled={disabled}
      />

      <div className="action-row">
        <button className="primary-button" type="button" disabled={disabled || !value.trim()} onClick={() => void onSend(value)}>
          Send
        </button>
        <button className="ghost-button" type="button" disabled={disabled} onClick={() => void onPull()}>
          Pull recommendation
        </button>
        <button className="ghost-button" type="button" disabled={disabled} onClick={() => void onBrief()}>
          Open brief
        </button>
      </div>
    </section>
  );
}
