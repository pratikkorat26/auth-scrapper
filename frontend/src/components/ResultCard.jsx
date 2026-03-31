function SnippetViewer({ title, snippet, compact = false, variant = "" }) {
  const lines = snippet ? snippet.split("\n") : [];
  const languageLabel = variant === "partial" ? "Partial HTML markup" : "Primary HTML evidence";

  return (
    <div className={`snippet-block${compact ? " snippet-block-compact" : ""}${variant ? ` snippet-block-${variant}` : ""}`}>
      <div className="snippet-header">
        {compact ? <h4>{title}</h4> : <h3>{title}</h3>}
        <span className="snippet-language">{languageLabel}</span>
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
          <div className="snippet-empty">
            <strong>No snippet was returned for this pass.</strong>
            <span>The analysis may still be useful, but there was no primary HTML excerpt to feature.</span>
          </div>
        )}
      </div>
    </div>
  );
}

const STATUS_COPY = {
  found: "Auth surface found",
  partial_auth_surface: "Partial auth surface found",
  blocked_or_inconclusive: "Analysis was limited",
  not_found: "No auth surface found",
};

const MODE_COPY = {
  static_html: "Static HTML",
  browser_primary: "Rendered browser pass",
  browser_fallback: "Rendered browser pass",
};

function toDisplayLabel(value) {
  return value
    ?.replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function buildSummary(result, statusLabel, modeLabel) {
  if (result.message) {
    return result.message;
  }

  if (result.status === "found") {
    return `The detector found a likely authentication surface during the ${modeLabel.toLowerCase()} and returned the strongest snippet it could verify.`;
  }

  if (result.status === "partial_auth_surface") {
    return `The detector found a partial entry point to authentication during the ${modeLabel.toLowerCase()}, but the evidence was not complete.`;
  }

  if (result.status === "blocked_or_inconclusive") {
    return `The run stayed inconclusive after the ${modeLabel.toLowerCase()}, so this should be treated as a limited read rather than a final answer.`;
  }

  return `${statusLabel} after the ${modeLabel.toLowerCase()}.`;
}

export default function ResultCard({ result }) {
  if (!result) {
    return null;
  }

  const normalizedStatus = result.status || (result.found ? "found" : "not_found");
  const statusLabel = STATUS_COPY[normalizedStatus] || toDisplayLabel(normalizedStatus) || "Analysis result";
  const modeLabel = MODE_COPY[result.analysis_mode] || toDisplayLabel(result.analysis_mode) || "Standard pass";
  const summary = buildSummary(result, statusLabel, modeLabel);
  const metadata = [
    { label: "Mode", value: modeLabel },
    { label: "Confidence", value: result.confidence ?? "N/A" },
    { label: "Fallback", value: result.fallback_used ? "Used" : "Not needed" },
    { label: "Interaction", value: result.interaction_used ? "Triggered" : "Not used" },
    { label: "AI review", value: result.ai_used ? (result.ai_refined ? "Gemini refined" : "Gemini assisted") : "Not used" },
  ];

  if (result.ai_provider) {
    metadata.push({ label: "Provider", value: result.ai_provider });
  }

  return (
    <section className="card result-card">
      <div className="result-header">
        <div className="result-heading">
          <p className="result-kicker">Analysis report</p>
          <h2>{statusLabel}</h2>
        </div>
        <span className={`pill pill-status pill-${normalizedStatus}`}>
          {statusLabel}
        </span>
      </div>

      <p className="analysis-summary">{summary}</p>

      <dl className="meta-row" aria-label="Analysis metadata">
        {metadata.map((item) => (
          <div className="meta-item" key={item.label}>
            <dt>{item.label}</dt>
            <dd>{item.value}</dd>
          </div>
        ))}
      </dl>

      <div className="report-grid">
        <section className="report-panel">
          <div className="panel-label">Page reviewed</div>
          <p className="report-text report-url">{result.url || "No URL returned"}</p>
        </section>

        <section className="report-panel">
          <div className="panel-label">Signals observed</div>
          <p className="report-text">
            {result.signals?.length ? result.signals.map(toDisplayLabel).join(", ") : "No explicit signals were reported."}
          </p>
        </section>

        <section className="report-panel report-panel-wide">
          <div className="panel-label">Run notes</div>
          <p className="report-text">
            {result.message || "No additional run notes were returned for this analysis."}
          </p>
        </section>
      </div>

      <SnippetViewer title="Primary Snippet" snippet={result.snippet} />

      {result.status === "partial_auth_surface" && result.partial_html_markup && (
        <SnippetViewer
          title="Partial Auth Surface Markup"
          snippet={result.partial_html_markup}
          variant="partial"
        />
      )}
    </section>
  );
}
