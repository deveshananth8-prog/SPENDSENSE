"""SpendSense AI FastAPI entrypoint (Stage 2: SQLite, Auth, Demo, Profile & Isolation)."""

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
import tempfile

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.db import SessionLocal, init_db
from app.routers import ai, auth, pages, profile
from app.security import (
    AuthRequiredRedirect,
    CSRF_COOKIE_NAME,
    get_or_issue_csrf_token,
    limiter,
    set_csrf_cookie,
)
from app.services.ai_client import is_ai_configured
from app.services.user_data import cleanup_expired_demos

BASE_DIR = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


def _ensure_upload_dir() -> None:
    try:
        settings.avatar_upload_path.mkdir(parents=True, exist_ok=True)
        if not os.access(settings.avatar_upload_path, os.W_OK | os.X_OK):
            raise PermissionError(f"Upload dir {settings.avatar_upload_path} is not writable")
    except OSError as exc:
        fallback = Path(tempfile.gettempdir()) / "spendsense_uploads" / "avatars"
        fallback.mkdir(parents=True, exist_ok=True)
        logger.warning(
            "Upload directory %s unavailable (%s); falling back to %s.",
            settings.upload_dir,
            exc,
            fallback,
        )
        settings.upload_dir = str(fallback)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        if settings.environment.lower() == "production" and settings.secret_key in {
            "",
            "dev-stage2-change-me-in-production",
            "change-me-to-a-long-random-secret",
        }:
            logger.warning("Production started with default SECRET_KEY; set a strong random SECRET_KEY environment variable.")
        if not is_ai_configured():
            logger.warning("GEMINI_API_KEY is missing or unset; SpendSense AI features will run in offline mode.")
        _ensure_upload_dir()
        init_db()
        with SessionLocal() as db:
            cleanup_expired_demos(db)
    except Exception as exc:
        logger.exception("SpendSense FastAPI startup failed: %s", exc)
        raise
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.middleware("http")
async def security_and_csrf_middleware(request: Request, call_next):
    token = get_or_issue_csrf_token(request)
    response = await call_next(request)
    if CSRF_COOKIE_NAME not in request.cookies:
        set_csrf_cookie(response, token, request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


@app.exception_handler(AuthRequiredRedirect)
async def auth_redirect_handler(_request: Request, exc: AuthRequiredRedirect):
    return RedirectResponse(url=f"/signin?next={exc.next_url}", status_code=303)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, _exc: RateLimitExceeded):
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many AI requests. Please wait a minute and try again."},
        )
    return RedirectResponse(url=f"{request.url.path}?rate_limited=1", status_code=429)


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.include_router(pages.router)
app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(ai.router)


@app.get("/health")
async def health():
    return {"status": "ok", "stage": 5}


if __name__ == "__main__":
    import sys
    import uvicorn

    try:
        port = int(os.environ.get("PORT", "3000") or "3000")
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=port,
            proxy_headers=True,
            forwarded_allow_ips="*",
        )
    except Exception as exc:
        logger.exception("Fatal error launching SpendSense uvicorn server: %s", exc)
        sys.exit(1)

