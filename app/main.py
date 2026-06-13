import base64
import os
import secrets
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from .database import engine, Base
from .routers import auth, jobs, craftsmen, availability, bids, reviews, categories, notifications

app = FastAPI(title="Verktorg.is API", version="1.0.0", docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


STAGING_AUTH_USER = os.environ.get("STAGING_AUTH_USER")
STAGING_AUTH_PASS = os.environ.get("STAGING_AUTH_PASS")


class StagingAuthMiddleware(BaseHTTPMiddleware):
    """Gate the whole site behind HTTP Basic Auth while in staging.

    Activated only when STAGING_AUTH_USER/STAGING_AUTH_PASS are set, so it's a
    no-op locally and can be turned off for public launch by removing the env vars.
    """

    async def dispatch(self, request, call_next):
        # CORS preflight and the health check must stay open: preflight requests
        # never carry credentials, and hosts poll /api/health without auth.
        if request.url.path == "/api/health" or request.method == "OPTIONS":
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        user = pwd = ""
        if auth_header.startswith("Basic "):
            try:
                user, _, pwd = base64.b64decode(auth_header[6:]).decode().partition(":")
            except Exception:
                pass

        if secrets.compare_digest(user, STAGING_AUTH_USER) and secrets.compare_digest(pwd, STAGING_AUTH_PASS):
            return await call_next(request)

        # JSON body so the frontend's api() helper (which always calls res.json())
        # doesn't throw on an empty 401 response.
        return JSONResponse(
            status_code=401,
            content={"detail": "Unauthorized"},
            headers={"WWW-Authenticate": 'Basic realm="Verktorg staging"'},
        )


if STAGING_AUTH_USER and STAGING_AUTH_PASS:
    app.add_middleware(StagingAuthMiddleware)

app.include_router(auth.router)
app.include_router(jobs.router)
app.include_router(craftsmen.router)
app.include_router(availability.router)
app.include_router(bids.router)
app.include_router(reviews.router)
app.include_router(categories.router)
app.include_router(notifications.router)

# Serve frontend static files
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/frontend", StaticFiles(directory=str(frontend_dir)), name="frontend")


@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/")
async def root():
    from fastapi.responses import FileResponse
    index = frontend_dir / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"message": "Verktorg.is API - see /api/docs for documentation"}
