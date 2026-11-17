"""Authentication routes: Sign up, Sign in, Log out, and Try the Demo."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.security import (
    clear_session_cookie,
    get_optional_user,
    get_or_issue_csrf_token,
    hash_password,
    limiter,
    sanitize_next_url,
    set_session_cookie,
    verify_csrf_token,
    verify_password,
)
from app.services.money import format_money, get_currency_list, load_currency_catalog
from app.services.user_data import cleanup_expired_demos, create_demo_user, user_view_dict

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["format_money"] = format_money
templates.env.globals["csrf_token"] = get_or_issue_csrf_token

router = APIRouter()


@router.get("/signin", response_class=HTMLResponse)
async def signin_page(
    request: Request,
    next: str = "/home",
    user: User | None = Depends(get_optional_user),
):
    if user is not None:
        return RedirectResponse(url="/home", status_code=303)
    return templates.TemplateResponse(
        request,
        "pages/signin.html",
        {
            "active_nav": "signin",
            "user": None,
            "next_url": sanitize_next_url(next),
            "error_msg": None,
            "email_value": "",
        },
    )


@router.post("/signin", response_class=HTMLResponse)
@limiter.limit("20/minute")
async def signin_submit(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    next: str = Form("/home"),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    verify_csrf_token(request, csrf_token)
    clean_email = email.strip().lower()
    safe_next = sanitize_next_url(next)

    user = db.query(User).filter(User.email == clean_email).first() if clean_email else None
    if not user or not password or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "pages/signin.html",
            {
                "active_nav": "signin",
                "user": None,
                "next_url": safe_next,
                "error_msg": "Invalid email or password.",
                "email_value": email.strip(),
            },
            status_code=400,
        )

    resp = RedirectResponse(url=safe_next, status_code=303)
    set_session_cookie(resp, user.id, request)
    return resp


@router.get("/signup", response_class=HTMLResponse)
async def signup_page(
    request: Request,
    user: User | None = Depends(get_optional_user),
):
    if user is not None:
        return RedirectResponse(url="/home", status_code=303)
    return templates.TemplateResponse(
        request,
        "pages/signup.html",
        {
            "active_nav": "signup",
            "user": None,
            "currencies": get_currency_list(),
            "error_msg": None,
            "form_values": {"name": "", "email": "", "currency": "INR"},
        },
    )


@router.post("/signup", response_class=HTMLResponse)
@limiter.limit("15/minute")
async def signup_submit(
    request: Request,
    name: str = Form(""),
    email: str = Form(""),
    currency: str = Form("INR"),
    password: str = Form(""),
    confirm_password: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    verify_csrf_token(request, csrf_token)
    clean_name = name.strip()
    clean_email = email.strip().lower()
    clean_currency = currency.strip().upper() or "INR"
    valid_currencies = load_currency_catalog().get("currencies", {})

    error_msg = None
    if len(clean_name) < 2:
        error_msg = "Please enter your name (at least 2 characters)."
    elif "@" not in clean_email or "." not in clean_email.split("@")[-1]:
        error_msg = "Please enter a valid email address."
    elif clean_currency not in valid_currencies:
        error_msg = "Please choose a supported currency."
    elif len(password) < 8:
        error_msg = "Password must be at least 8 characters long."
    elif password != confirm_password:
        error_msg = "Password and confirmation do not match."
    elif db.query(User).filter(User.email == clean_email).first() is not None:
        error_msg = "An account with that email already exists. Please sign in instead."

    if error_msg:
        return templates.TemplateResponse(
            request,
            "pages/signup.html",
            {
                "active_nav": "signup",
                "user": None,
                "currencies": get_currency_list(),
                "error_msg": error_msg,
                "form_values": {
                    "name": clean_name,
                    "email": email.strip(),
                    "currency": clean_currency if clean_currency in valid_currencies else "INR",
                },
            },
            status_code=400,
        )

    new_user = User(
        name=clean_name,
        email=clean_email,
        password_hash=hash_password(password),
        currency_code=clean_currency,
        theme="system",
        is_demo=False,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    resp = RedirectResponse(url="/home", status_code=303)
    set_session_cookie(resp, new_user.id, request)
    return resp


@router.post("/logout")
async def logout(
    request: Request,
    csrf_token: str = Form(""),
):
    verify_csrf_token(request, csrf_token)
    resp = RedirectResponse(url="/", status_code=303)
    clear_session_cookie(resp, request)
    return resp


@router.post("/demo")
@limiter.limit("20/minute")
async def try_demo(
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    verify_csrf_token(request, csrf_token)
    cleanup_expired_demos(db)
    demo_user = create_demo_user(db)
    resp = RedirectResponse(url="/home", status_code=303)
    set_session_cookie(resp, demo_user.id, request)
    return resp
