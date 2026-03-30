export default function UrlForm({ url, onChange, onSubmit, isLoading }) {
  return (
    <form className="card form-card" onSubmit={onSubmit}>
      <label className="field-label" htmlFor="url">
        Website URL
      </label>
      <div className="input-row">
        <input
          id="url"
          className="url-input"
          type="url"
          placeholder="https://example.com/login"
          value={url}
          onChange={(event) => onChange(event.target.value)}
          required
        />
        <button className="primary-button" type="submit" disabled={isLoading}>
          {isLoading ? "Analyzing..." : "Analyze"}
        </button>
      </div>
    </form>
  );
}

