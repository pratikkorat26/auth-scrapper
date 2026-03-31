const ANALYSIS_STAGES = [
  { label: "Rendered capture", detail: "Loads the page in a browser and records a few DOM snapshots of the visible auth state." },
  { label: "Rule-based detection", detail: "Scores each snapshot for visible login, OAuth, multi-step, and passwordless auth signals." },
  { label: "Best snippet selection", detail: "Keeps the strongest visible auth markup and preserves distinct secondary auth components when they exist." },
];

export default function AnalysisFlowModal({ isOpen, onClose }) {
  if (!isOpen) {
    return null;
  }

  return (
    <div
      className="modal-overlay"
      role="presentation"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <section className="modal-card" role="dialog" aria-modal="true" aria-labelledby="auth-extraction-title">
        <div className="modal-header">
          <div>
            <p className="modal-kicker">How auth extraction works</p>
            <h2 id="auth-extraction-title">Current evaluation flow</h2>
          </div>
          <button className="modal-close" type="button" aria-label="Close dialog" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="modal-stage-list">
          {ANALYSIS_STAGES.map((stage) => (
            <article className="modal-stage" key={stage.label}>
              <span className="modal-stage-title">{stage.label}</span>
              <p>{stage.detail}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
