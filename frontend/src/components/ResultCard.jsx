export default function ResultCard({ result }) {
  if (!result) {
    return null;
  }

  const snippetLines = result.snippet ? result.snippet.split("\n") : [];

  return (
    <section className="card">
      <div className="result-header">
        <h2>Analysis Result</h2>
        <span className={`pill ${result.found ? "pill-success" : "pill-muted"}`}>
          {result.found ? "Found" : "Not Found"}
        </span>
      </div>

      <dl className="result-grid">
        <div>
          <dt>URL</dt>
          <dd>{result.url}</dd>
        </div>
        <div>
          <dt>Confidence</dt>
          <dd>{result.confidence}</dd>
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
