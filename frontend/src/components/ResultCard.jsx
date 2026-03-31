function SnippetViewer({ title, snippet, compact = false }) {
  const lines = snippet ? snippet.split("\n") : [];

  return (
    <div className={`snippet-block${compact ? " snippet-block-compact" : ""}`}>
      <div className="snippet-header">
        {compact ? <h4>{title}</h4> : <h3>{title}</h3>}
        <span className="snippet-language">HTML</span>
      </div>
      <div className={`snippet-viewer${compact ? " snippet-viewer-compact" : ""}`} aria-label={`${title} viewer`}>
        {lines.length ? (
          <pre className={`snippet-code${compact ? " snippet-code-compact" : ""}`}>
            <code>
              {lines.map((line, index) => (
                <span className="snippet-line" key={`${title}-${index}-${line}`}>
                  <span className="snippet-line-number" aria-hidden="true">
                    {index + 1}
                  </span>
                  <span className="snippet-line-content">{line || " "}</span>
                </span>
              ))}
            </code>
          </pre>
        ) : (
          <div className="snippet-empty">No HTML snippet returned.</div>
        )}
      </div>
    </div>
  );
}

export default function ResultCard({ result }) {
  if (!result) {
    return null;
  }

  const statusLabel = result.status?.replaceAll("_", " ") || (result.found ? "found" : "not found");

  return (
    <section className="card">
      <div className="result-header">
        <h2>Analysis Result</h2>
        <span className={`pill pill-status pill-${result.status || (result.found ? "found" : "not_found")}`}>
          {statusLabel}
        </span>
      </div>

      <div className="result-summary">
        <div className="summary-chip">{result.analysis_mode === "browser_fallback" ? "Browser Fallback" : "Static HTML"}</div>
        <div className="summary-chip">Confidence {result.confidence}</div>
        {result.fallback_used ? <div className="summary-chip">Fallback Used</div> : null}
        {result.interaction_used ? <div className="summary-chip">Interaction Reveal</div> : null}
        {result.ai_used ? <div className="summary-chip">Gemini Used</div> : null}
        {result.ai_refined ? <div className="summary-chip">Gemini Refined</div> : null}
        {result.ai_provider ? <div className="summary-chip">{result.ai_provider}</div> : null}
      </div>

      <dl className="result-grid">
        <div>
          <dt>URL</dt>
          <dd>{result.url}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{statusLabel}</dd>
        </div>
        <div>
          <dt>Signals</dt>
          <dd>{result.signals.length ? result.signals.join(", ") : "None"}</dd>
        </div>
        <div>
          <dt>Message</dt>
          <dd>{result.message}</dd>
        </div>
      </dl>

      <SnippetViewer title="Primary Snippet" snippet={result.snippet} />
    </section>
  );
}
