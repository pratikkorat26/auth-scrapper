# Auth Detector

A full-stack authentication detection app that analyzes a public web page, renders dynamic routes when needed, and returns login-related HTML snippets plus a list of detected authentication components.

## Overview

- Backend: FastAPI
- Frontend: React with Vite
- HTML parsing: BeautifulSoup with `lxml`
- HTTP client: `httpx`
- Browser rendering: Playwright
- AI fallback: Gemini (`google-genai`)

The app accepts a URL, fetches the page, runs deterministic auth detection first, optionally renders the page in Playwright, and uses Gemini for low-confidence or dynamic auth surfaces. The response includes a primary snippet and a `components` array with all detected auth surfaces.

## Architecture

- `backend/`
  - FastAPI app with fetch, detector, browser, and Gemini services
- `frontend/`
  - Single-page UI for URL submission and result inspection
- `.github/workflows/ci.yml`
  - Backend pytest and frontend production build

## Detection Flow

1. Validate the submitted URL.
2. Fetch HTML with `httpx`.
3. Parse it with BeautifulSoup and score heuristic auth candidates.
4. If the page looks dynamic or incomplete, render it with Playwright and rerun detection on the rendered DOM.
5. If the result is partial, inconclusive, or low-confidence, call Gemini with:
   - extracted auth-focused HTML
   - the heuristic summary
   - an optional Playwright screenshot
6. Normalize Gemini output into:
   - a primary auth snippet
   - multiple auth components
   - top-level status and confidence

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
  "confidence": 0.94,
  "signals": ["password_input", "username_or_email_input"],
  "snippet": "<form>...</form>",
  "message": "Authentication component detected.",
  "analysis_mode": "static",
  "fallback_used": false,
  "interaction_used": false,
  "ai_used": false,
  "ai_refined": false,
  "ai_provider": null,
  "ai_model": null,
  "components": [
    {
      "type": "traditional",
      "surface_type": "form",
      "confidence": 0.94,
      "selector_hint": "form",
      "signals": ["password_input", "username_or_email_input"],
      "providers": [],
      "fields": [
        {
          "type": "email",
          "label": "Username or email address",
          "name": "login"
        }
      ],
      "snippet": "<form>...</form>",
      "summary": "Traditional login form"
    }
  ]
}
```

## Configuration

Relevant backend environment variables:

- `APP_ENV`
- `LOG_LEVEL`
- `REQUEST_TIMEOUT_SECONDS`
- `MAX_SNIPPET_LENGTH`
- `FRONTEND_ORIGIN`
- `ENABLE_BROWSER_FALLBACK`
- `BROWSER_TIMEOUT_SECONDS`
- `BROWSER_HEADLESS`
- `ENABLE_LIMITED_AUTH_REVEAL`
- `ENABLE_SAFE_IDENTITY_TYPING`
- `ENABLE_AI_FALLBACK`
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `AI_LOW_CONFIDENCE_THRESHOLD`
- `AI_MAX_INPUT_CHARS`
- `ENABLE_AI_SCREENSHOT_CONTEXT`

Gemini fallback is disabled by default. Enable it by setting:

```env
ENABLE_AI_FALLBACK=true
GEMINI_API_KEY=your-key
```

## Running Tests

```bash
cd backend
pytest
```

## Detection Logic Notes

- `traditional`: password form or equivalent final login form
- `oauth`: social/SSO provider auth cluster
- `passwordless`: passkey, magic-link, OTP, or WebAuthn style auth
- `multi_step`: email-first or username-first auth surface
- `challenge`: blocked, captcha, or anti-bot challenge surface

The top-level `snippet` is selected from the highest-priority component in this order:

1. `traditional`
2. `multi_step`
3. `oauth`
4. `passwordless`
5. `challenge`

## Limitations

- Some sites block automation or show challenge pages instead of auth UI.
- Gemini improves hard-page coverage, but it adds latency and depends on API availability.
- Selector hints returned by AI are best-effort hints, not guaranteed stable selectors.
- The app intentionally detects auth components only; it never submits credentials.

## Example Websites To Try

1. `https://github.com/login`
2. `https://account.box.com/login`
3. `https://www.reddit.com/login/`
4. `https://substack.com/sign-in`
5. `https://apply.coveredca.com/static/lw-web/login`

## CI

GitHub Actions runs:

- backend tests with `pytest`
- frontend production build with `vite build`
