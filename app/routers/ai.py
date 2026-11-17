"""Stage 4 AI & Quick Add backend API routes.

All Gemini SDK calls are strictly server-side, authenticated per-user,
CSRF-protected, input-capped, and rate-limited per user.
"""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import MerchantCategory, Transaction, User
from app.security import ai_user_rate_key, limiter, require_api_user, verify_csrf_token
from app.services.ai_client import (
    ask_money_buddy,
    explain_affordability_ai,
    generate_home_narrative_ai,
    is_ai_configured,
    parse_quick_add_screenshot_ai,
    parse_quick_add_text_ai,
    suggest_category_ai,
)
from app.services.money import format_money, load_currency_catalog
from app.services.parsers import normalize_merchant, to_minor_units
from app.services.snapshot import build_financial_snapshot
from data.sample_data import CATEGORIES

router = APIRouter(prefix="/api", tags=["ai"])

ALLOWED_IMAGE_FORMATS = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


def _get_merchant_memory(db: Session, user_id: int) -> dict[str, str]:
    rows = (
        db.query(MerchantCategory)
        .filter(MerchantCategory.user_id == user_id)
        .all()
    )
    return {r.merchant_normalized: r.category for r in rows}


def _remember_merchant_category(db: Session, user_id: int, merchant: str, category: str) -> None:
    norm = normalize_merchant(merchant)
    if not norm or category not in CATEGORIES:
        return
    existing = (
        db.query(MerchantCategory)
        .filter(
            MerchantCategory.user_id == user_id,
            MerchantCategory.merchant_normalized == norm,
        )
        .first()
    )
    if existing:
        existing.category = category
    else:
        db.add(
            MerchantCategory(
                user_id=user_id,
                merchant_normalized=norm,
                category=category,
            )
        )


def _locale_for_currency(code: str) -> str:
    catalog = load_currency_catalog().get("currencies", {})
    meta = catalog.get(code.upper())
    return meta["locale"] if meta else "en_US"


class MoneyBuddyRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)


class QuickAddTextRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)


class SuggestCategoryRequest(BaseModel):
    description: str = Field(default="", max_length=200)


class QuickSaveRequest(BaseModel):
    merchant: str = Field(..., min_length=1, max_length=120)
    amount: str | float | int
    currency: str = Field(..., min_length=3, max_length=3)
    category: str
    date: str
    type: Literal["expense", "income"] = "expense"
    confirm_currency_mismatch: bool = False


class AffordabilityExplainRequest(BaseModel):
    item: str = Field(default="this purchase", max_length=120)
    verdict: str = Field(..., max_length=32)
    balance_formatted: str = Field(..., max_length=40)
    essentials_formatted: str = Field(..., max_length=40)
    purchase_formatted: str = Field(..., max_length=40)
    safe_to_spend_formatted: str = Field(..., max_length=40)
    left_after_buying_formatted: str = Field(..., max_length=40)
    daily_before_formatted: str = Field(..., max_length=40)
    daily_after_formatted: str = Field(..., max_length=40)
    tight_threshold_formatted: str = Field(..., max_length=40)
    days: int = Field(..., ge=1, le=365)


@router.post("/ai/money-buddy")
@limiter.limit("30/minute", key_func=ai_user_rate_key)
async def api_money_buddy(
    request: Request,
    payload: MoneyBuddyRequest,
    user: User = Depends(require_api_user),
    db: Session = Depends(get_db),
):
    verify_csrf_token(request, None)
    snapshot = build_financial_snapshot(db, user)
    try:
        res = ask_money_buddy(payload.question, snapshot)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return res.model_dump()


@router.post("/ai/quick-add/parse")
@limiter.limit("30/minute", key_func=ai_user_rate_key)
async def api_quick_add_parse(
    request: Request,
    payload: QuickAddTextRequest,
    user: User = Depends(require_api_user),
    db: Session = Depends(get_db),
):
    verify_csrf_token(request, None)
    mem = _get_merchant_memory(db, user.id)
    try:
        parsed, offline_mode = parse_quick_add_text_ai(
            payload.text,
            user_currency=user.currency_code,
            merchant_memory=mem,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "amount": str(parsed.amount),
        "amount_minor": parsed.amount_minor,
        "currency": parsed.currency,
        "user_currency": user.currency_code,
        "currency_mismatch": parsed.currency != user.currency_code,
        "merchant": parsed.merchant,
        "category": parsed.category,
        "date": parsed.date,
        "type": parsed.type,
        "offline_mode": offline_mode,
    }


@router.post("/ai/quick-add/screenshot")
@limiter.limit("15/minute", key_func=ai_user_rate_key)
async def api_quick_add_screenshot(
    request: Request,
    screenshot: UploadFile = File(...),
    user: User = Depends(require_api_user),
    db: Session = Depends(get_db),
):
    verify_csrf_token(request, request.headers.get("X-CSRF-Token"))
    raw = await screenshot.read(settings.ai_max_image_bytes + 1)
    if not raw:
        raise HTTPException(status_code=400, detail="Please choose a payment screenshot image.")
    if len(raw) > settings.ai_max_image_bytes:
        raise HTTPException(status_code=400, detail="Screenshot must be 4 MB or smaller.")

    try:
        with Image.open(io.BytesIO(raw)) as img:
            img_format = (img.format or "").upper()
            img.verify()
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(status_code=400, detail="Upload a valid JPEG, PNG, or WebP payment screenshot.")

    mime_type = ALLOWED_IMAGE_FORMATS.get(img_format)
    if not mime_type:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, or WebP screenshots are supported.")

    mem = _get_merchant_memory(db, user.id)
    try:
        parsed, offline_mode = parse_quick_add_screenshot_ai(
            raw,
            mime_type,
            user_currency=user.currency_code,
            merchant_memory=mem,
        )
    except RuntimeError as exc:
        return JSONResponse(
            status_code=503,
            content={"detail": str(exc), "offline_mode": True},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except TimeoutError:
        return JSONResponse(
            status_code=504,
            content={"detail": "Screenshot scanning timed out after 10 seconds. Please try again or paste SMS text.", "offline_mode": False},
        )
    except Exception as exc:
        code = getattr(exc, "code", None)
        if code == 429:
            return JSONResponse(
                status_code=429,
                content={"detail": "AI screenshot quota reached right now. Paste the SMS or type an expense like 'chai 20' instead.", "offline_mode": True},
            )
        return JSONResponse(
            status_code=503,
            content={"detail": "Screenshot scanning is temporarily busy. Please try again in a moment or paste your SMS text.", "offline_mode": True},
        )

    return {
        "amount": str(parsed.amount),
        "amount_minor": parsed.amount_minor,
        "currency": parsed.currency,
        "user_currency": user.currency_code,
        "currency_mismatch": parsed.currency != user.currency_code,
        "merchant": parsed.merchant,
        "category": parsed.category,
        "date": parsed.date,
        "type": parsed.type,
        "offline_mode": offline_mode,
    }


@router.post("/expenses/quick-save", status_code=201)
@limiter.limit("40/minute", key_func=ai_user_rate_key)
async def api_quick_save_expense(
    request: Request,
    payload: QuickSaveRequest,
    user: User = Depends(require_api_user),
    db: Session = Depends(get_db),
):
    verify_csrf_token(request, None)
    clean_currency = payload.currency.strip().upper()
    catalog = load_currency_catalog().get("currencies", {})
    if clean_currency not in catalog:
        raise HTTPException(status_code=400, detail="Unsupported currency code.")

    if clean_currency != user.currency_code and not payload.confirm_currency_mismatch:
        return JSONResponse(
            status_code=409,
            content={
                "detail": f"Detected currency ({clean_currency}) differs from your account currency ({user.currency_code}). Confirm before saving.",
                "requires_currency_confirmation": True,
                "detected_currency": clean_currency,
                "user_currency": user.currency_code,
            },
        )

    try:
        amt_dec = Decimal(str(payload.amount).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400, detail="Please enter a valid positive amount.")
    if amt_dec <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero.")

    try:
        tx_date = date.fromisoformat(payload.date.strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Please select a valid date.")

    clean_merchant = payload.merchant.strip()[:120]
    if not clean_merchant:
        raise HTTPException(status_code=400, detail="Merchant or description is required.")

    clean_category = payload.category if payload.category in CATEGORIES else "Other"
    amount_minor = to_minor_units(amt_dec, clean_currency)
    if amount_minor <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero.")

    tx = Transaction(
        user_id=user.id,
        amount_minor=amount_minor,
        currency_code=clean_currency,
        category=clean_category,
        date=tx_date,
        description="Quick Add entry",
        merchant=clean_merchant,
        type=payload.type,
        essential=False,
        method="UPI" if clean_currency == "INR" else "Card",
    )
    db.add(tx)
    _remember_merchant_category(db, user.id, clean_merchant, clean_category)
    db.commit()
    db.refresh(tx)

    locale = _locale_for_currency(clean_currency)
    return {
        "id": tx.id,
        "date": tx.date.isoformat(),
        "merchant": tx.merchant,
        "note": tx.description,
        "category": tx.category,
        "currency": tx.currency_code,
        "type": tx.type,
        "method": tx.method,
        "amount_minor": tx.amount_minor,
        "amount_formatted": format_money(tx.amount_minor, tx.currency_code, locale),
        "remembered_merchant": True,
    }


@router.post("/ai/suggest-category")
@limiter.limit("60/minute", key_func=ai_user_rate_key)
async def api_suggest_category(
    request: Request,
    payload: SuggestCategoryRequest,
    user: User = Depends(require_api_user),
    db: Session = Depends(get_db),
):
    verify_csrf_token(request, None)
    mem = _get_merchant_memory(db, user.id)
    try:
        res = suggest_category_ai(payload.description, merchant_memory=mem)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return res.model_dump()


@router.post("/ai/home-narrative")
@limiter.limit("20/minute", key_func=ai_user_rate_key)
async def api_home_narrative(
    request: Request,
    user: User = Depends(require_api_user),
    db: Session = Depends(get_db),
):
    verify_csrf_token(request, None)
    snapshot = build_financial_snapshot(db, user)
    res = generate_home_narrative_ai(snapshot)
    return res.model_dump()


@router.post("/ai/explain-affordability")
@limiter.limit("30/minute", key_func=ai_user_rate_key)
async def api_explain_affordability(
    request: Request,
    payload: AffordabilityExplainRequest,
    user: User = Depends(require_api_user),
):
    verify_csrf_token(request, None)
    res = explain_affordability_ai(payload.model_dump())
    return res.model_dump()
