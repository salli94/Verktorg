# Verktorg.is

Verktorg.is is a marketplace MVP that connects Icelandic customers with tradespeople and small contractors.

## Architecture

This repo is currently a modular monolith:

- `app/` contains the FastAPI backend
- `frontend/` contains the same-origin Alpine.js + Tailwind frontend
- `frontend/src/` is now the TypeScript source for the browser app
- `frontend/dist/` is the compiled browser output
- the backend serves the frontend directly

For the current product stage this should stay monolithic. Splitting frontend and backend would add deployment and contract overhead before it solves a real blocker.

## Local Run

### Docker

```bash
docker-compose up --build
```

The app will be available at `http://localhost:8000`.

### Native Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm --prefix frontend install
npm --prefix frontend run build
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend TypeScript

```bash
npm --prefix frontend install
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

## Environment Variables

- `DATABASE_URL` default: `sqlite+aiosqlite:///./verktorg.db`
- `JWT_SECRET` default: development-only fallback in code; set a real secret in production
- `STAGING_AUTH_USER` optional: enables full-site staging basic auth
- `STAGING_AUTH_PASS` optional: enables full-site staging basic auth

You can start from:

```bash
cp .env.example .env
```

## Tests

```bash
pytest
```

## Current Product Notes

- Core marketplace flows are in place for auth, jobs, bids, craftsman profiles, availability, and notifications.
- The UI and API are tuned for a same-origin deployment.
- Before a public launch, use a production database, set a real JWT secret, and keep product copy aligned with implemented trust features.
