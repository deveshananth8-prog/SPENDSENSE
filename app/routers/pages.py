"""Page routes with Stage 2 authentication protection and user-scoped data."""

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.security import get_optional_user, get_or_issue_csrf_token, require_user
from app.services.money import format_money
from app.services.stage1_data import get_landing_context
from app.services.user_data import (
    build_before_you_spend_context,
    build_budgets_context,
    build_expenses_context,
    build_goals_context,
    build_home_context,
    build_money_buddy_context,
    user_view_dict,
)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["format_money"] = format_money
templates.env.globals["csrf_token"] = get_or_issue_csrf_token

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def landing_page(
    request: Request,
    user: User | None = Depends(get_optional_user),
):
    ctx = get_landing_context()
    ctx["user"] = user_view_dict(user) if user else None
    return templates.TemplateResponse(request, "pages/landing.html", ctx)


@router.get("/home", response_class=HTMLResponse)
async def home_page(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    ctx = build_home_context(db, user)
    return templates.TemplateResponse(request, "pages/home.html", ctx)


@router.get("/before-you-spend", response_class=HTMLResponse)
async def before_you_spend_page(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    ctx = build_before_you_spend_context(db, user)
    return templates.TemplateResponse(request, "pages/before_you_spend.html", ctx)


@router.get("/money-buddy", response_class=HTMLResponse)
async def money_buddy_page(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    ctx = build_money_buddy_context(db, user)
    return templates.TemplateResponse(request, "pages/money_buddy.html", ctx)


@router.get("/expenses", response_class=HTMLResponse)
async def expenses_page(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    ctx = build_expenses_context(db, user)
    return templates.TemplateResponse(request, "pages/expenses.html", ctx)


@router.get("/budgets", response_class=HTMLResponse)
async def budgets_page(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    ctx = build_budgets_context(db, user)
    return templates.TemplateResponse(request, "pages/budgets.html", ctx)


@router.get("/goals", response_class=HTMLResponse)
async def goals_page(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    ctx = build_goals_context(db, user)
    return templates.TemplateResponse(request, "pages/goals.html", ctx)
