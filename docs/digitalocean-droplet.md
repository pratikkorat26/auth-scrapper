# DigitalOcean Droplet Docker Deployment

This repo can be deployed as a single Docker container on a DigitalOcean Droplet.

## What The Container Does

- builds the Vite frontend
- runs the FastAPI backend
- serves the built frontend and backend API from the same public origin
- includes Playwright Chromium for browser-based auth detection

## Local Docker Verification

Build the image from the repo root:

```bash
docker build -t auth-detector .
```

Run it locally:

```bash
docker run --rm -p 8000:8000 \
  -e APP_ENV=production \
  -e LOG_LEVEL=INFO \
  -e REQUEST_TIMEOUT_SECONDS=30 \
  -e MAX_SNIPPET_LENGTH=800 \
  -e FRONTEND_ORIGIN=http://localhost:8000 \
  -e ENABLE_BROWSER_FALLBACK=true \
  -e BROWSER_TIMEOUT_SECONDS=45 \
  -e BROWSER_HEADLESS=true \
  -e ENABLE_LIMITED_AUTH_REVEAL=true \
  -e ENABLE_SAFE_IDENTITY_TYPING=true \
  auth-detector
```

Verify:

- `http://localhost:8000/`
- `http://localhost:8000/health`
- `POST http://localhost:8000/api/v1/analyze`

## Droplet Setup

Recommended target:

- Ubuntu Droplet
- Docker installed on the host
- one public IPv4 address

Basic host setup:

```bash
sudo apt-get update
sudo apt-get install -y docker.io
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
```

Log out and back in after adding your user to the `docker` group.

## Deploy The Container

Copy the repo to the Droplet, or pull it from GitHub, then build the image:

```bash
docker build -t auth-detector .
```

Run the container:

```bash
docker run -d \
  --name auth-detector \
  --restart unless-stopped \
  -p 80:8000 \
  -e APP_ENV=production \
  -e LOG_LEVEL=INFO \
  -e REQUEST_TIMEOUT_SECONDS=30 \
  -e MAX_SNIPPET_LENGTH=800 \
  -e FRONTEND_ORIGIN=http://your-domain-or-ip \
  -e ENABLE_BROWSER_FALLBACK=true \
  -e BROWSER_TIMEOUT_SECONDS=45 \
  -e BROWSER_HEADLESS=true \
  -e ENABLE_LIMITED_AUTH_REVEAL=true \
  -e ENABLE_SAFE_IDENTITY_TYPING=true \
  auth-detector
```

If you later add HTTPS with a reverse proxy, set `FRONTEND_ORIGIN` to the final public `https://` origin.

## Runtime Notes

- `VITE_API_BASE_URL` is optional in this deployment mode because frontend and backend share the same origin
- the backend API stays available at `/api/v1/analyze`
- health checks stay available at `/health`
- Playwright-heavy analysis can still be slower than static HTML analysis

## Recommended Next Step

For a production-facing domain, add a reverse proxy such as Caddy or Nginx in front of the container so you can terminate TLS cleanly and expose the app over HTTPS.
