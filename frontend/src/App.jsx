import { useState } from "react";

import { analyzeUrl } from "./api/client";
import ResultCard from "./components/ResultCard";
import StatusBanner from "./components/StatusBanner";
import UrlForm from "./components/UrlForm";
import "./styles.css";

export default function App() {
  const [url, setUrl] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setIsLoading(true);
    setError("");

    try {
      const nextResult = await analyzeUrl(url.trim());
      setResult(nextResult);
    } catch (submissionError) {
      setResult(null);
      setError(submissionError.message);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <section className="hero">
        <p className="eyebrow">AI Engineer Assessment</p>
        <h1>Authentication Component Detector</h1>
        <p className="lead">
          Submit a public website URL and inspect the strongest login-related HTML snippet the backend can
          detect with deterministic parsing rules.
        </p>
      </section>

      <UrlForm url={url} onChange={setUrl} onSubmit={handleSubmit} isLoading={isLoading} />
      <StatusBanner type="error" message={error} />
      <ResultCard result={result} />
    </main>
  );
}

