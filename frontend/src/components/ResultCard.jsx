export default function ResultCard({ result }) {
  if (!result) {
    return null;
  }

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
        <h3>Snippet</h3>
        <pre>{result.snippet || "No HTML snippet returned."}</pre>
      </div>
    </section>
  );
}

