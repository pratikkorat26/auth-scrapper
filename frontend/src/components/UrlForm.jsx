export default function UrlForm({ url, onChange, onSubmit, isLoading }) {
  return (
    <form className="card form-card" onSubmit={onSubmit}>
      <div className="form-intro">
        <p className="form-kicker">Analyze a page</p>
        <label className="field-label" htmlFor="url">
          Enter a public URL
        </label>
        <p className="field-help">
          Paste a login page, homepage, or app shell to review its auth surface.
        </p>
      </div>

      <div className="input-row">
        <div className="input-stack">
          <input
            id="url"
            className="url-input"
            type="url"
            placeholder="https://example.com/login"
            value={url}
            onChange={(event) => onChange(event.target.value)}
            required
            disabled={isLoading}
            aria-describedby="url-guidance"
          />
          <p className="guidance-text" id="url-guidance">
            Example: `https://example.com/login`
          </p>
        </div>

        <button className="primary-button" type="submit" disabled={isLoading}>
          <span className={`button-dot${isLoading ? " button-dot-active" : ""}`} aria-hidden="true" />
          {isLoading ? "Running analysis" : "Analyze page"}
        </button>
      </div>
    </form>
  );
}
