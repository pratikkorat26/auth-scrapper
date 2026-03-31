.PHONY: check backend-check frontend-check

backend-check:
	cd backend && ./.venv/bin/pytest

frontend-check:
	cd frontend && npm run build

check: backend-check frontend-check
