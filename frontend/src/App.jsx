import { useEffect, useState } from "react";

import { analyzeUrl } from "./api/client";
import ResultCard from "./components/ResultCard";
import StatusBanner from "./components/StatusBanner";
import UrlForm from "./components/UrlForm";
import "./styles.css";

const ANALYSIS_STAGES = [
  { label: "Rendered capture", detail: "Loads the page in a browser and records a few DOM snapshots of the visible auth state." },
  { label: "Rule-based detection", detail: "Scores each snapshot for visible login, OAuth, multi-step, and passwordless auth signals." },
  { label: "Best snippet selection", detail: "Keeps the strongest visible auth markup and preserves distinct secondary auth components when they exist." },
  { label: "Optional AI audit", detail: "Uses Gemini only as a non-authoritative audit for ambiguous cases without replacing the detector result." },
];

export default function App() {
  const [url, setUrl] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);

  useEffect(() => {
    if (!isModalOpen) {
      return undefined;
    }

    function handleKeydown(event) {
      if (event.key === "Escape") {
        setIsModalOpen(false);
      }
    }

    window.addEventListener("keydown", handleKeydown);

    return () => {
      window.removeEventListener("keydown", handleKeydown);
    };
  }, [isModalOpen]);

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
      <div className="page-glow page-glow-one" aria-hidden="true" />
      <div className="page-glow page-glow-two" aria-hidden="true" />

      <section className="hero card hero-card">
        <div className="hero-topline">
          <p className="eyebrow">Auth surface review</p>
          <button className="hero-link" type="button" onClick={() => setIsModalOpen(true)}>
            How auth extraction works
          </button>
        </div>

        <div className="hero-copy">
          <h1>Review sign-in surfaces faster.</h1>
          <p className="lead">Paste a public URL to get a clean readout and the strongest auth snippet we can verify.</p>
        </div>
      </section>

      <section className="main-column">
        <UrlForm url={url} onChange={setUrl} onSubmit={handleSubmit} isLoading={isLoading} />
        <StatusBanner type="error" message={error} />

        {isLoading ? (
          <section className="card state-card state-card-loading" aria-live="polite">
            <div className="state-kicker">Analysis in progress</div>
            <h2>Checking the page and looking for the strongest auth evidence.</h2>
            <p>
              The app is rendering the page, comparing a few visible auth states, and selecting the strongest
              auth snippet it can verify.
            </p>
            <div className="loading-meter" aria-hidden="true">
              <span />
            </div>
          </section>
        ) : null}

        {!isLoading && !result && !error ? (
          <section className="card state-card state-card-empty">
            <div className="state-kicker">Ready when you are</div>
            <h2>Start with any public page that likely exposes sign in, sign up, or account entry points.</h2>
            <p>
              The first pass is built to feel complete even before a result appears, so you always know where
              to begin and what kind of evidence will come back.
            </p>
          </section>
        ) : null}

        <ResultCard result={result} />
      </section>

      <footer className="app-signature" aria-label="Built by signature">
        <p>Built by Pratik Korat</p>
        <span>Made with love ❤️</span>
      </footer>

      {isModalOpen ? (
        <div
          className="modal-overlay"
          role="presentation"
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              setIsModalOpen(false);
            }
          }}
        >
          <section className="modal-card" role="dialog" aria-modal="true" aria-labelledby="auth-extraction-title">
            <div className="modal-header">
              <div>
                <p className="modal-kicker">How auth extraction works</p>
                <h2 id="auth-extraction-title">Current evaluation flow</h2>
              </div>
              <button
                className="modal-close"
                type="button"
                aria-label="Close dialog"
                onClick={() => setIsModalOpen(false)}
              >
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
      ) : null}
    </main>
  );
}
