# Auth Detector

A full-stack assessment project that accepts any public URL, inspects the page for authentication UI, and returns the best auth-related HTML snippet plus structured component metadata.

## Assessment Fit

This project directly covers the technical assessment requirements:

- Scrapes and analyzes website markup
- Accepts dynamic URL input through a UI and API
- Detects authentication components such as login forms, OAuth buttons, email-first flows, and passwordless entry points
- Returns the relevant HTML snippet or reports that no auth surface was found

## Stack

- Backend: FastAPI
- Frontend: React with Vite
- Parsing: BeautifulSoup with `lxml`
- Rendering: Playwright

## How It Works

The app uses a Playwright-first, rule-based detection flow:

1. Accept a URL from the UI or API.
2. Render the page and capture a few bounded DOM snapshots.
3. Run deterministic auth detection on each snapshot.
4. Pick the strongest visible auth surface and return the most relevant snippet plus structured metadata.

## What The App Returns

- A top-level status: `found`, `partial_auth_surface`, `blocked_or_inconclusive`, or `not_found`
- A status label and analysis mode label derived from the backend contract
- The best auth-related HTML snippet, plus `partial_html_markup` when only a partial auth surface is available
- Structured `components` metadata, including surface type, providers, fields, and signals
- Run metadata including `fallback_used`, `interaction_used`, and `protected_page`

### Statuses

- `found`: a strong auth surface was identified
- `partial_auth_surface`: some auth entry-point evidence was found, but the surface was incomplete
- `blocked_or_inconclusive`: analysis was limited by a challenge, blocked page, or inconclusive markup
- `not_found`: no meaningful auth surface was detected

### Analysis Modes

- `browser_primary`: the rendered browser pass produced the final answer
- `static_html`: the browser path failed and the final answer came from static HTML fetching

`protected_page` is not a separate detector mode. It is a derived flag that is set when the final result is `blocked_or_inconclusive` and the response message indicates a blocked or challenged page.

The app never submits credentials. It only inspects public auth markup.

## Tested Sites

The detector was built and manually validated against these real-world login surfaces across multiple product categories.

| URL | Category | Expected Auth Style | Why It Matters |
| --- | --- | --- | --- |
| `https://github.com/login` | Developer Platform | `traditional` | Standard login form with secondary auth options and passkey support |
| `https://accounts.spotify.com/en/login` | Music Streaming | `traditional` | Consumer login flow with modern wrapper-heavy rendering |
| `https://www.eventbrite.com/signin/` | Event Platform | `mixed traditional + oauth` | Consumer auth surface with multiple sign-in options |
| `https://account.box.com/login` | Cloud Storage | `multi_step` | Enterprise-style dynamic auth shell with staged identity flow |
| `https://slack.com/signin#/signin` | Workplace Collaboration | `multi_step` | JS-heavy workspace login with multi-step routing |
| `https://www.linkedin.com/login` | Professional Network | `traditional` | Large real-world login page with nested auth layout |
| `https://stackoverflow.com/users/login` | Developer Community | `mixed traditional + oauth` | Mixed auth page with traditional and provider-based options |
| `https://substack.com/sign-in` | Publishing Platform | `multi_step` | Email-first sign-in flow with follow-up auth actions |
| `https://www.facebook.com/login` | Social Network | `traditional` | High-traffic login page useful for testing wrapper-heavy detection |
| `https://account.booking.com/sign-in` | Travel Booking | `multi_step` | Consumer sign-in flow with staged identity-first interaction |
| `https://www.dropbox.com/login` | File Sharing | `traditional` | Cloud login page with modern rendered auth structure |
| `https://www.coursera.org/login` | Online Learning | `mixed traditional + oauth` | Mixed auth experience with consumer and provider-based entry points |

These are representative evidence sites for the assessment, and the app also supports arbitrary public URLs.

## How To Evaluate In 5 Minutes

### Backend

```bash
cd backend
/opt/homebrew/bin/python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
uvicorn app.main:app --reload
```

Backend runs on `http://localhost:8000`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on `http://localhost:5173`.

### Verification

From the repo root:

```bash
make check
```

That runs the backend test suite and the frontend production build using the committed project workflow.

### Quick API Check

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"url":"https://github.com/login"}'
```

Then open the frontend, paste a public URL, and inspect the returned auth markup.

## Sample Response

```json
{
  "url": "https://github.com/login",
  "found": true,
  "status": "found",
  "status_label": "Auth surface found",
  "confidence": 0.94,
  "signals": ["password_input", "username_or_email_input", "submit_button"],
  "snippet": "<form>...</form>",
  "partial_html_markup": null,
  "message": "Authentication component detected.",
  "analysis_mode": "browser_primary",
  "analysis_mode_label": "Rendered browser pass",
  "protected_page": false,
  "fallback_used": false,
  "interaction_used": false,
  "components": [
    {
      "type": "traditional",
      "surface_type": "form",
      "confidence": 0.94,
      "selector_hint": "form",
      "signals": ["password_input", "username_or_email_input", "submit_button"],
      "providers": [],
      "fields": [
        { "type": "email", "name": "login" },
        { "type": "password", "name": "password" }
      ],
      "snippet": "<form>...</form>",
      "summary": "Authentication component detected."
    }
  ]
}
```

## Environment Notes

- Python 3.12 recommended
- Node 18+ recommended
- Playwright Chromium install required for best results
- Backend settings come from `backend/.env`, based on `backend/.env.example`
- Important runtime settings include browser timeout/headless mode, frontend origin, fallback behavior, and limited auth reveal toggles
- `VITE_API_BASE_URL` is optional for same-origin deployments such as a single Docker container

## Limitations

- Some sites show CAPTCHA, rate limits, or anti-bot challenges instead of login UI.
- Some auth flows are region-specific or depend on previous user state.
- Dynamic pages are handled with Playwright snapshots, but heavily protected sites may still be limited.
- The backend returns structured `components`, `providers`, `fields`, and snippets; the current frontend emphasizes summary text, snippets, signals, and run metadata rather than a full structured component explorer.

## Tests

Project-level verification:

```bash
make check
```

Backend-only tests:

```bash
cd backend
./.venv/bin/pytest
```

Current CI checks:

- backend pytest
- frontend production build

## Additional Submission Docs

- [Assessment Summary](docs/assessment-summary.md)
- [Tested Sites Evidence](docs/tested-sites.md)
- [DigitalOcean Droplet Docker Deployment](docs/digitalocean-droplet.md)
