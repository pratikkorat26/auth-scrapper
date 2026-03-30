export default function ResultCard({ result }) {
  if (!result) {
    return null;
  }

  const snippetLines = result.snippet ? result.snippet.split("\n") : [];
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
        {result.surface_type ? <div className="summary-chip">{result.surface_type.replaceAll("_", " ")}</div> : null}
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

      {result.alternate_candidates?.length ? (
        <section className="alternate-panel">
          <h3>Alternate Candidates</h3>
          <ul className="alternate-list">
            {result.alternate_candidates.map((candidate, index) => (
              <li key={`${candidate.surface_type}-${index}`}>
                <strong>{candidate.surface_type.replaceAll("_", " ")}</strong>
                <span>
                  {candidate.status.replaceAll("_", " ")} • confidence {candidate.confidence}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <div className="snippet-block">
        <div className="snippet-header">
          <h3>Snippet</h3>
          <span className="snippet-language">HTML</span>
        </div>

        <div className="snippet-viewer" aria-label="HTML snippet viewer">
          {snippetLines.length ? (
            <pre className="snippet-code">
              <code>
                {snippetLines.map((line, index) => (
                  <span className="snippet-line" key={`${index}-${line}`}>
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
    </section>
  );
}
