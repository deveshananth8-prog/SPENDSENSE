"""Profile settings, theme persistence, avatar upload/serving, and account deletion routes."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from babel.numbers import get_currency_precision
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User
from app.security import (
    clear_session_cookie,
    get_or_issue_csrf_token,
    hash_password,
    limiter,
    require_api_user,
    require_user,
    verify_csrf_token,
    verify_password,
)
from app.services.avatars import AvatarValidationError, delete_avatar_file, process_and_save_avatar
from app.services.money import format_money
from app.services.user_data import (
    build_profile_context,
    convert_user_currency,
    delete_user_account,
    preview_currency_conversion,
)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["format_money"] = format_money
templates.env.globals["csrf_token"] = get_or_issue_csrf_token

router = APIRouter()


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    user: User = Depends(require_user),
):
    ctx = build_profile_context(user)
    return templates.TemplateResponse(request, "pages/profile.html", ctx)


@router.post("/profile/info", response_class=HTMLResponse)
async def update_profile_info(
    request: Request,
    display_name: str = Form(""),
    allowance: str = Form("0"),
    tight_threshold: str = Form(""),
    next_income: str = Form(""),
    csrf_token: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    verify_csrf_token(request, csrf_token)
    clean_name = display_name.strip()
    if len(clean_name) < 2:
        ctx = build_profile_context(user, info_error="Display name must be at least 2 characters.")
        return templates.TemplateResponse(request, "pages/profile.html", ctx, status_code=400)

    precision = get_currency_precision(user.currency_code)
    scale = Decimal(10) ** precision
    try:
        dec_val = Decimal(allowance.strip() or "0")
        if dec_val < 0:
            raise ValueError("negative")
        allowance_minor = int((dec_val * scale).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        ctx = build_profile_context(user, info_error="Please enter a valid non-negative allowance amount.")
        return templates.TemplateResponse(request, "pages/profile.html", ctx, status_code=400)

    threshold_minor = user.tight_threshold_minor
    if tight_threshold.strip():
        try:
            t_dec = Decimal(tight_threshold.strip())
            if t_dec < 0:
                raise ValueError("negative")
            threshold_minor = int((t_dec * scale).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        except (InvalidOperation, ValueError):
            ctx = build_profile_context(user, info_error="Please enter a valid non-negative daily comfort floor.")
            return templates.TemplateResponse(request, "pages/profile.html", ctx, status_code=400)

    parsed_date = None
    if next_income.strip():
        try:
            parsed_date = date.fromisoformat(next_income.strip())
        except ValueError:
            ctx = build_profile_context(user, info_error="Please choose a valid next income date.")
            return templates.TemplateResponse(request, "pages/profile.html", ctx, status_code=400)

    db_user = db.query(User).filter(User.id == user.id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    db_user.name = clean_name
    db_user.monthly_allowance_minor = allowance_minor
    db_user.tight_threshold_minor = threshold_minor
    db_user.next_income_date = parsed_date
    db.commit()
    db.refresh(db_user)

    ctx = build_profile_context(db_user, info_success="Profile details saved.")
    return templates.TemplateResponse(request, "pages/profile.html", ctx)


@router.post("/profile/currency/preview")
async def preview_profile_currency(
    request: Request,
    target_currency: str = Form(""),
    csrf_token: str = Form(""),
    user: User = Depends(require_api_user),
    db: Session = Depends(get_db),
):
    verify_csrf_token(request, csrf_token)
    code = target_currency.strip().upper()
    if not code:
        try:
            body = await request.json()
            code = str(body.get("target_currency") or "").strip().upper()
        except Exception:
            code = ""
    try:
        return JSONResponse(preview_currency_conversion(db, user, code))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/profile/currency/convert", response_class=HTMLResponse)
async def convert_profile_currency(
    request: Request,
    target_currency: str = Form(""),
    csrf_token: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    verify_csrf_token(request, csrf_token)
    code = target_currency.strip().upper()
    try:
        updated_user = convert_user_currency(db, user, code)
    except ValueError as exc:
        ctx = build_profile_context(user, currency_error=str(exc))
        return templates.TemplateResponse(request, "pages/profile.html", ctx, status_code=400)

    ctx = build_profile_context(
        updated_user,
        currency_success=f"Working currency switched to {updated_user.currency_code} and amounts converted.",
    )
    return templates.TemplateResponse(request, "pages/profile.html", ctx)


@router.post("/profile/theme")
async def update_profile_theme(
    request: Request,
    theme: str = Form("system"),
    csrf_token: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    verify_csrf_token(request, csrf_token)
    clean_theme = theme.strip().lower()
    if clean_theme not in {"light", "dark", "system"}:
        clean_theme = "system"

    db_user = db.query(User).filter(User.id == user.id).first()
    if db_user:
        db_user.theme = clean_theme
        db.commit()
        db.refresh(db_user)

    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"theme": clean_theme})
    return RedirectResponse(url="/profile", status_code=303)


@router.post("/profile/password", response_class=HTMLResponse)
@limiter.limit("10/minute")
async def update_profile_password(
    request: Request,
    current_password: str = Form(""),
    new_password: str = Form(""),
    confirm_new_password: str = Form(""),
    csrf_token: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    verify_csrf_token(request, csrf_token)
    db_user = db.query(User).filter(User.id == user.id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(current_password, db_user.password_hash):
        ctx = build_profile_context(db_user, pw_error="Current password is incorrect.")
        return templates.TemplateResponse(request, "pages/profile.html", ctx, status_code=400)
    if len(new_password) < 8:
        ctx = build_profile_context(db_user, pw_error="New password must be at least 8 characters.")
        return templates.TemplateResponse(request, "pages/profile.html", ctx, status_code=400)
    if new_password != confirm_new_password:
        ctx = build_profile_context(db_user, pw_error="New password and confirmation do not match.")
        return templates.TemplateResponse(request, "pages/profile.html", ctx, status_code=400)

    db_user.password_hash = hash_password(new_password)
    db.commit()
    ctx = build_profile_context(db_user, pw_success="Password updated successfully.")
    return templates.TemplateResponse(request, "pages/profile.html", ctx)


@router.post("/profile/avatar", response_class=HTMLResponse)
async def upload_profile_avatar(
    request: Request,
    avatar: UploadFile = File(...),
    csrf_token: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    verify_csrf_token(request, csrf_token)
    raw = await avatar.read(2 * 1024 * 1024 + 1)
    try:
        new_filename = process_and_save_avatar(raw)
    except AvatarValidationError as exc:
        ctx = build_profile_context(user, avatar_error=str(exc))
        return templates.TemplateResponse(request, "pages/profile.html", ctx, status_code=400)

    db_user = db.query(User).filter(User.id == user.id).first()
    if not db_user:
        delete_avatar_file(new_filename)
        raise HTTPException(status_code=404, detail="User not found")

    old_filename = db_user.avatar_filename
    db_user.avatar_filename = new_filename
    db.commit()
    db.refresh(db_user)
    if old_filename and old_filename != new_filename:
        delete_avatar_file(old_filename)

    ctx = build_profile_context(db_user, avatar_success="Profile picture updated.")
    return templates.TemplateResponse(request, "pages/profile.html", ctx)


@router.post("/profile/avatar/remove")
async def remove_profile_avatar(
    request: Request,
    csrf_token: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    verify_csrf_token(request, csrf_token)
    db_user = db.query(User).filter(User.id == user.id).first()
    if db_user and db_user.avatar_filename:
        old = db_user.avatar_filename
        db_user.avatar_filename = None
        db.commit()
        delete_avatar_file(old)
    return RedirectResponse(url="/profile", status_code=303)


@router.post("/profile/delete")
async def delete_account(
    request: Request,
    confirm_delete: str = Form(""),
    csrf_token: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    verify_csrf_token(request, csrf_token)
    if confirm_delete != "yes":
        ctx = build_profile_context(user, info_error="Account deletion requires confirmation.")
        return templates.TemplateResponse(request, "pages/profile.html", ctx, status_code=400)

    db_user = db.query(User).filter(User.id == user.id).first()
    if db_user:
        delete_user_account(db, db_user)

    resp = RedirectResponse(url="/", status_code=303)
    clear_session_cookie(resp, request)
    return resp


@router.get("/avatars/{filename}")
async def serve_user_avatar(
    filename: str,
    user: User = Depends(require_user),
):
    safe_name = Path(filename).name
    if not user.avatar_filename or user.avatar_filename != safe_name:
        raise HTTPException(status_code=404, detail="Avatar not found")
    file_path = settings.avatar_upload_path / safe_name
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Avatar not found")
    return FileResponse(
        path=file_path,
        media_type="image/webp",
        headers={"Cache-Control": "private, max-age=3600"},
    )
