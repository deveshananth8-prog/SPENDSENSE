"""Security utilities: argon2 hashing, signed HttpOnly sessions, CSRF tokens, rate limiting."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import quote

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User

SESSION_COOKIE_NAME = "spendsense_session"
CSRF_COOKIE_NAME = "spendsense_csrf"

_hasher = PasswordHasher()
limiter = Limiter(key_func=get_remote_address)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def _sign(payload_b64: str) -> str:
    sig = hmac.new(
        settings.secret_key.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")


def _pack(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"{payload_b64}.{_sign(payload_b64)}"


def _unpack(token: str) -> dict | None:
    if not token or "." not in token:
        return None
    parts = token.split(".", 1)
    if len(parts) != 2:
        return None
    payload_b64, sig = parts
    expected_sig = _sign(payload_b64)
    if not hmac.compare_digest(sig, expected_sig):
        return None
    try:
        padding = "=" * (-len(payload_b64) % 4)
        raw = base64.urlsafe_b64decode(payload_b64 + padding)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            return None
        exp = data.get("exp")
        if exp is not None and int(exp) < int(time.time()):
            return None
        return data
    except Exception:
        return None


def create_session_token(user_id: int) -> str:
    return _pack(
        {
            "uid": user_id,
            "exp": int(time.time()) + settings.session_max_age_seconds,
            "nonce": secrets.token_hex(8),
        }
    )


def verify_session_token(token: str | None) -> int | None:
    if not token:
        return None
    data = _unpack(token)
    if not data:
        return None
    uid = data.get("uid")
    return int(uid) if isinstance(uid, int) else None


def is_https_request(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    if request.url.scheme == "https" or proto == "https":
        return True
    forwarded_host = request.headers.get("x-forwarded-host", "").split(",")[0].strip().lower().split(":")[0]
    host = request.headers.get("host", "").split(":")[0].lower()
    if forwarded_host.endswith(".run.app") or host.endswith(".run.app"):
        return True
    origin = request.headers.get("origin", "").lower()
    referer = request.headers.get("referer", "").lower()
    return origin.startswith("https://") or referer.startswith("https://")


def cookie_transport_kwargs(request: Request | None = None) -> dict:
    https = (request is not None and is_https_request(request)) or settings.environment == "production"
    if https:
        return {"secure": True, "samesite": "none"}
    return {"secure": False, "samesite": "lax"}


def _append_partitioned(response: Response, cookie_name: str) -> None:
    existing = response.headers.getlist("set-cookie")
    if not existing:
        return
    del response.headers["set-cookie"]
    for header in existing:
        if header.startswith(f"{cookie_name}=") and "; partitioned" not in header.lower():
            header = f"{header}; Partitioned"
        response.headers.append("set-cookie", header)


def set_csrf_cookie(response: Response, token: str, request: Request | None = None) -> None:
    kwargs = cookie_transport_kwargs(request)
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        max_age=settings.session_max_age_seconds,
        httponly=False,
        path="/",
        **kwargs,
    )
    if kwargs["secure"]:
        _append_partitioned(response, CSRF_COOKIE_NAME)


def set_session_cookie(response: Response, user_id: int, request: Request | None = None) -> None:
    token = create_session_token(user_id)
    kwargs = cookie_transport_kwargs(request)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        path="/",
        **kwargs,
    )
    if kwargs["secure"]:
        _append_partitioned(response, SESSION_COOKIE_NAME)


def clear_session_cookie(response: Response, request: Request | None = None) -> None:
    kwargs = cookie_transport_kwargs(request)
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        **kwargs,
    )
    if kwargs["secure"]:
        _append_partitioned(response, SESSION_COOKIE_NAME)


def create_csrf_token() -> str:
    return _pack(
        {
            "csrf": secrets.token_hex(16),
            "exp": int(time.time()) + settings.session_max_age_seconds,
        }
    )


def get_or_issue_csrf_token(request: Request) -> str:
    existing = request.cookies.get(CSRF_COOKIE_NAME)
    if existing and _unpack(existing) is not None:
        return existing
    if hasattr(request.state, "csrf_token") and request.state.csrf_token:
        return request.state.csrf_token
    token = create_csrf_token()
    request.state.csrf_token = token
    return token


def verify_csrf_token(request: Request, submitted_token: str | None) -> None:
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    header_token = request.headers.get("X-CSRF-Token")
    candidate = submitted_token or header_token
    if (
        not cookie_token
        or not candidate
        or _unpack(cookie_token) is None
        or not hmac.compare_digest(cookie_token, candidate)
    ):
        raise HTTPException(status_code=403, detail="Invalid or missing CSRF token.")


def sanitize_next_url(next_url: str | None, default: str = "/home") -> str:
    if not next_url:
        return default
    # Only allow internal relative paths starting with single '/'
    if next_url.startswith("/") and not next_url.startswith("//") and "\\" not in next_url:
        return next_url
    return default


class AuthRequiredRedirect(Exception):
    def __init__(self, next_url: str):
        self.next_url = next_url


def get_optional_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    uid = verify_session_token(token)
    if uid is None:
        return None
    user = db.query(User).filter(User.id == uid).first()
    return user


def require_user(
    request: Request,
    user: User | None = Depends(get_optional_user),
) -> User:
    if user is None:
        path = request.url.path
        if request.url.query:
            path = f"{path}?{request.url.query}"
        raise AuthRequiredRedirect(next_url=quote(path, safe="/?=&"))
    return user
