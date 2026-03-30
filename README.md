# Auth Detector

A small full-stack application that analyzes a public web page and tries to find a likely authentication or login component using deterministic HTML rules.

## Overview

- Backend: FastAPI
- Frontend: React with Vite
- HTML parsing: BeautifulSoup with `lxml`
- HTTP client: `httpx`

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
6. Return the highest-scoring candidate snippet, confidence, and signals.

## Setup

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
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
  "confidence": 0.95,
  "signals": [
    "password_input",
    "username_or_email_input",
    "submit_button",
    "auth_keyword"
  ],
  "snippet": "<form>...</form>",
  "message": "Authentication component detected."
}
```

## Running Tests

```bash
cd backend
pytest
```

## Limitations

- Only works on raw server-rendered HTML returned by the target URL.
- JavaScript-rendered or post-login flows may not expose auth markup in the initial response.
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

