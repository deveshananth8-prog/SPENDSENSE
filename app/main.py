"""SpendSense AI FastAPI entrypoint (Stage 2: SQLite, Auth, Demo, Profile & Isolation)."""

from contextlib import asynccontextmanager
from pathlib import Path

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
from app.services.user_data import cleanup_expired_demos

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.avatar_upload_path.mkdir(parents=True, exist_ok=True)
    init_db()
    with SessionLocal() as db:
        cleanup_expired_demos(db)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.middleware("http")
async def csrf_cookie_middleware(request: Request, call_next):
    token = get_or_issue_csrf_token(request)
    response = await call_next(request)
    if CSRF_COOKIE_NAME not in request.cookies:
        set_csrf_cookie(response, token, request)
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
    return {"status": "ok", "stage": 4}
