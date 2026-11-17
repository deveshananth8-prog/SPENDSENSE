"""Thin Stage 1 page routes serving Jinja2 templates with hard-coded sample data."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.services.money import format_money
from app.services.stage1_data import (
    get_before_you_spend_context,
    get_budgets_context,
    get_expenses_context,
    get_goals_context,
    get_home_context,
    get_landing_context,
    get_money_buddy_context,
    get_profile_context,
)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["format_money"] = format_money

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    ctx = get_landing_context()
    return templates.TemplateResponse(request, "pages/landing.html", ctx)


@router.get("/signin", response_class=HTMLResponse)
async def signin_page(request: Request):
    return templates.TemplateResponse(
        request,
        "pages/signin.html",
        {"active_nav": "signin", "user": None},
    )


@router.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    ctx = get_profile_context()
    ctx["active_nav"] = "signup"
    return templates.TemplateResponse(request, "pages/signup.html", ctx)


@router.get("/home", response_class=HTMLResponse)
async def home_page(request: Request):
    ctx = get_home_context()
    return templates.TemplateResponse(request, "pages/home.html", ctx)


@router.get("/before-you-spend", response_class=HTMLResponse)
async def before_you_spend_page(request: Request):
    ctx = get_before_you_spend_context()
    return templates.TemplateResponse(request, "pages/before_you_spend.html", ctx)


@router.get("/money-buddy", response_class=HTMLResponse)
async def money_buddy_page(request: Request):
    ctx = get_money_buddy_context()
    return templates.TemplateResponse(request, "pages/money_buddy.html", ctx)


@router.get("/expenses", response_class=HTMLResponse)
async def expenses_page(request: Request):
    ctx = get_expenses_context()
    return templates.TemplateResponse(request, "pages/expenses.html", ctx)


@router.get("/budgets", response_class=HTMLResponse)
async def budgets_page(request: Request):
    ctx = get_budgets_context()
    return templates.TemplateResponse(request, "pages/budgets.html", ctx)


@router.get("/goals", response_class=HTMLResponse)
async def goals_page(request: Request):
    ctx = get_goals_context()
    return templates.TemplateResponse(request, "pages/goals.html", ctx)


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    ctx = get_profile_context()
    return templates.TemplateResponse(request, "pages/profile.html", ctx)
