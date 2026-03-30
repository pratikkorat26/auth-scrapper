# Auth Detector

A small full-stack application that analyzes a public web page and tries to find a likely authentication or login component using deterministic HTML rules.

## Overview

- Backend: FastAPI
- Frontend: React with Vite
- HTML parsing: BeautifulSoup with `lxml`
- HTTP client: `httpx`
- Dynamic-page fallback: Playwright

The user submits a URL. The backend fetches the HTML, parses it, scores likely authentication components, and returns the strongest matching HTML snippet or a not-found result.

## Architecture

- `backend/`
  - FastAPI API with configuration, structured logging, fetch service, detector service, and pytest coverage
- `frontend/`
  - Single-page React app that calls the API and renders the analysis result
- `.github/workflows/ci.yml`
  - Minimal CI for backend tests and frontend build

## Detection Flow

1. Validate and normalize a user-provided URL.
2. Fetch the document with `httpx` using async requests, redirects, and a timeout.
3. Confirm the response is HTML.
4. Parse the HTML with BeautifulSoup.
5. Score candidate elements using simple rule-based signals:
   - contains a password input
   - contains a likely username or email input nearby
   - contains a submit button
   - contains login or auth keywords in text or attributes
6. If the static HTML looks like an empty JavaScript app shell, optionally render it in a headless browser and rerun the same detector on the hydrated DOM.
7. Return a structured auth-surface result with status, extracted fields/actions/providers, analysis mode, and HTML snippet.

## Setup

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
uvicorn app.main:app --reload
```

Backend runs on `http://localhost:8000`.

From the repository root, this also works:

```bash
uvicorn backend.app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on `http://localhost:5173`.

## API Example

### Request

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"url":"https://github.com/login"}'
```

### Response

```json
{
  "url": "https://github.com/login",
  "found": true,
  "status": "found",
  "confidence": 0.95,
  "signals": [
    "password_input",
    "username_or_email_input",
    "submit_button",
    "auth_keyword"
  ],
  "snippet": "<form>...</form>",
  "message": "Authentication component detected.",
  "analysis_mode": "static",
  "fallback_used": false,
  "interaction_used": false,
  "surface_type": "form",
  "fields": [
    {
      "type": "email",
      "label": "Username or email address",
      "name": "login"
    }
  ],
  "actions": [
    {
      "type": "submit",
      "label": "Sign in"
    }
  ],
  "providers": [],
  "alternate_candidates": []
}
```

## Running Tests

```bash
cd backend
pytest
```

## Browser Fallback Setup

Some login pages render entirely in JavaScript. To support those, install the Playwright Chromium browser once:

```bash
cd backend
.venv/bin/python -m playwright install chromium
```

Relevant environment variables:

- `ENABLE_BROWSER_FALLBACK`
- `BROWSER_TIMEOUT_SECONDS`
- `BROWSER_HEADLESS`

## Live Validation Report

Run the live-site validation batch from the backend without starting the API server:

```bash
cd backend
.venv/bin/python -m app.validation.runner
```

The report classifies each target as:

- `pass`: authentication markup was detected
- `partial`: an auth surface was found, but it looked like SSO-first, email-first, or otherwise incomplete
- `miss`: the page fetched successfully, but the detector did not find auth markup
- `inconclusive`: the site timed out, blocked the request, redirected unexpectedly, or otherwise could not be judged fairly

This validation flow is intentionally local-only and is not part of GitHub Actions because third-party sites can change markup, rate-limit, or block automated requests.

## Benchmark Snapshot

Representative results from the current benchmark set:

| Site | Category | Result | Notes |
| --- | --- | --- | --- |
| GitHub | SaaS | `pass` | Strong static detection |
| Box | SaaS | `pass` | Static detection plus SSO signals |
| Facebook | Social | `pass` | Strong static detection |
| LinkedIn | Social | `pass` | Strong static detection |
| Times of India | News | `pass` | Static password form |
| Substack | Blogs | `partial` | Browser fallback reveals an auth surface without a clear final password step |
| Reddit | Blogs | `inconclusive` | Dynamic route timed out during browser fallback |
| Flipkart | E-Commerce | `inconclusive` | Generic auth-like surface but not enough evidence for a confident login form |
| NDTV | News | `inconclusive` | Upstream returned `403` |

## Limitations

- Static detection works best on classic forms; dynamic pages may require browser fallback and limited safe interaction.
- Some modern auth flows are SSO-first or multi-step, so they may return `partial_auth_surface` instead of a final password form.
- Anti-bot protection, rate limiting, gated routes, or delayed client rendering can still produce `blocked_or_inconclusive`.
- Confidence is heuristic and deterministic, not learned.
- The fetcher intentionally accepts only HTML responses over `http` or `https`.

## Example Websites To Try

1. `https://github.com/login`
2. `https://gitlab.com/users/sign_in`
3. `https://www.reddit.com/login/`
4. `https://stackoverflow.com/users/login`
5. `https://example.com`

## CI

GitHub Actions runs:

- backend tests with `pytest`
- frontend production build with `vite build`
