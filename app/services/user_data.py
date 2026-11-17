"""Database-backed user data queries and view-model builders.

Every query reading or writing user records MUST filter by user_id == user.id.
"""

from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Budget, Goal, Transaction, User
from app.security import hash_password
from app.services.avatars import delete_avatar_file
from app.services.money import format_money, get_currency_list, load_currency_catalog
from app.services.stage1_data import compute_before_you_spend, compute_runway
from data.sample_data import (
    CATEGORIES,
    RIYA_BUDGETS,
    RIYA_EXPENSES,
    RIYA_GOALS,
    RIYA_PROFILE,
)


def _locale_for_currency(currency_code: str) -> str:
    catalog = load_currency_catalog().get("currencies", {})
    meta = catalog.get(currency_code.upper())
    return meta["locale"] if meta else "en_US"


def user_initials(name: str) -> str:
    parts = [p for p in (name or "").strip().split() if p]
    if not parts:
        return "U"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def user_view_dict(user: User) -> dict[str, Any]:
    currency = user.currency_code or "INR"
    locale = _locale_for_currency(currency)
    next_income_str = user.next_income_date.isoformat() if user.next_income_date else ""
    days_until = (
        max((user.next_income_date - date.today()).days, 1)
        if user.next_income_date
        else 12
    )
    return {
        "id": user.id,
        "display_name": user.name,
        "initials": user_initials(user.name),
        "email": user.email,
        "currency": currency,
        "locale": locale,
        "theme": user.theme or "system",
        "avatar_url": f"/avatars/{user.avatar_filename}" if user.avatar_filename else "",
        "monthly_allowance_minor": user.monthly_allowance_minor,
        "monthly_allowance_formatted": format_money(user.monthly_allowance_minor, currency, locale),
        "tight_threshold_minor": user.tight_threshold_minor,
        "tight_threshold_formatted": format_money(user.tight_threshold_minor, currency, locale),
        "next_income_date": next_income_str,
        "days_until_income": days_until,
        "is_demo": bool(user.is_demo),
    }


def cleanup_expired_demos(db: Session, upload_dir: Path | None = None) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.demo_ttl_minutes)
    expired = (
        db.query(User)
        .filter(User.is_demo.is_(True), User.created_at < cutoff)
        .all()
    )
    count = len(expired)
    for demo_user in expired:
        delete_avatar_file(demo_user.avatar_filename, upload_dir=upload_dir)
        db.delete(demo_user)
    if count:
        db.commit()
    return count


def create_demo_user(db: Session) -> User:
    token = secrets.token_hex(6)
    today = date.today()
    demo_user = User(
        name="Riya Sharma",
        email=f"demo-{token}@spendsense.local",
        password_hash=hash_password(secrets.token_urlsafe(24)),
        currency_code="INR",
        theme="system",
        monthly_allowance_minor=RIYA_PROFILE["monthly_allowance_minor"],
        next_income_date=today + timedelta(days=RIYA_PROFILE["days_until_income"]),
        tight_threshold_minor=RIYA_PROFILE["tight_threshold_minor"],
        is_demo=True,
    )
    db.add(demo_user)
    db.flush()

    # Seed Riya's sample transactions shifted relative to today
    for idx, exp in enumerate(RIYA_EXPENSES):
        tx_date = today - timedelta(days=min(idx, 13))
        db.add(
            Transaction(
                user_id=demo_user.id,
                amount_minor=exp["amount_minor"],
                currency_code="INR",
                category=exp["category"],
                date=tx_date,
                description=exp["note"],
                merchant=exp["merchant"],
                type="expense",
                essential=bool(exp.get("essential", False)),
                method=exp.get("method", "UPI"),
            )
        )

    for b in RIYA_BUDGETS:
        db.add(
            Budget(
                user_id=demo_user.id,
                category=b["category"],
                limit_minor=b["limit_minor"],
            )
        )

    for g in RIYA_GOALS:
        db.add(
            Goal(
                user_id=demo_user.id,
                title=g["title"],
                target_minor=g["target_minor"],
                saved_minor=g["saved_minor"],
                deadline=date.fromisoformat(g["deadline"]),
                note=g["note"],
            )
        )

    db.commit()
    db.refresh(demo_user)
    return demo_user


def get_user_transactions(db: Session, user_id: int) -> list[Transaction]:
    return (
        db.query(Transaction)
        .filter(Transaction.user_id == user_id)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .all()
    )


def get_user_budgets(db: Session, user_id: int) -> list[Budget]:
    return (
        db.query(Budget)
        .filter(Budget.user_id == user_id)
        .order_by(Budget.id.asc())
        .all()
    )


def get_user_goals(db: Session, user_id: int) -> list[Goal]:
    return (
        db.query(Goal)
        .filter(Goal.user_id == user_id)
        .order_by(Goal.id.asc())
        .all()
    )


def delete_user_account(db: Session, user: User, upload_dir: Path | None = None) -> None:
    delete_avatar_file(user.avatar_filename, upload_dir=upload_dir)
    db.delete(user)
    db.commit()


def _estimate_balance_minor(user: User, transactions: list[Transaction]) -> int:
    if user.is_demo:
        return RIYA_PROFILE["current_balance_minor"]
    income_tx = sum(t.amount_minor for t in transactions if t.type == "income")
    expense_tx = sum(t.amount_minor for t in transactions if t.type != "income")
    return user.monthly_allowance_minor + income_tx - expense_tx


def build_home_context(db: Session, user: User) -> dict[str, Any]:
    u = user_view_dict(user)
    currency = u["currency"]
    locale = u["locale"]

    txs = get_user_transactions(db, user.id)
    goals = get_user_goals(db, user.id)

    expense_txs = [t for t in txs if t.type != "income"]
    total_expenses_minor = sum(t.amount_minor for t in expense_txs)
    balance_minor = _estimate_balance_minor(user, txs)
    essentials_minor = RIYA_PROFILE["upcoming_essentials_minor"] if user.is_demo else 0
    savings_minor = sum(g.saved_minor for g in goals)

    tx_dicts = [
        {
            "id": t.id,
            "date": t.date.isoformat(),
            "merchant": t.merchant,
            "note": t.description,
            "category": t.category,
            "amount_minor": t.amount_minor,
            "essential": t.essential,
            "method": t.method,
            "amount_formatted": format_money(t.amount_minor, currency, locale),
        }
        for t in expense_txs
    ]

    runway = compute_runway(
        balance_minor=balance_minor,
        essentials_minor=essentials_minor,
        days_until_income=u["days_until_income"],
        expenses=tx_dicts,
        today=date.today(),
        currency=currency,
        locale=locale,
    )

    cat_totals: dict[str, int] = {}
    for t in expense_txs:
        cat_totals[t.category] = cat_totals.get(t.category, 0) + t.amount_minor
    sorted_cats = sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)

    chart_data = {
        "labels": [c[0] for c in sorted_cats] if sorted_cats else ["No expenses yet"],
        "values_major": [float(Decimal(c[1]) / Decimal(100)) for c in sorted_cats] if sorted_cats else [1],
        "formatted": [format_money(c[1], currency, locale) for c in sorted_cats] if sorted_cats else [format_money(0, currency, locale)],
    }

    if tx_dicts:
        monthly_summary = (
            f"You have spent {format_money(total_expenses_minor, currency, locale)} against your "
            f"{u['monthly_allowance_formatted']} allowance. After setting aside "
            f"{format_money(essentials_minor, currency, locale)} for essentials, you can spend up to "
            f"{runway['formatted']['max_per_day']} a day without dipping early."
        )
    else:
        monthly_summary = (
            "No expenses logged yet. Add your monthly allowance in Profile or record your first expense "
            "to bring your Money Runway and category breakdown to life."
        )

    insights = [
        {
            "title": "Weekend spend runs 1.6x higher" if user.is_demo else "Daily pace check",
            "metric": "1.6x ratio" if user.is_demo else runway["formatted"]["avg_daily_spend"],
            "body": (
                f"Your weekend outings and late-night Zomato orders average {format_money(31250, currency, locale)} "
                f"per weekend vs {format_money(9629, currency, locale)}/day on weekdays."
                if user.is_demo
                else f"Your current daily pace is {runway['formatted']['avg_daily_spend']} with {u['days_until_income']} days until next income."
            ),
            "tone": "warn" if user.is_demo else "ok",
        },
        {
            "title": "Most frequent small spend: Evening chai" if user.is_demo else "Safe spending cushion",
            "metric": f"{format_money(4000, currency, locale)} each" if user.is_demo else runway["status"],
            "body": (
                f"Small tap-and-pay chai and snack trips stay well under budget, and cutting just two food delivery "
                f"orders frees {format_money(43000, currency, locale)} toward your headphones goal."
                if user.is_demo
                else "Test any upcoming purchase in Before You Spend before tapping pay."
            ),
            "tone": "ok",
        },
    ]

    return {
        "user": u,
        "active_nav": "home",
        "runway": runway,
        "kpis": {
            "balance": format_money(balance_minor, currency, locale),
            "balance_minor": balance_minor,
            "essentials_formatted": format_money(essentials_minor, currency, locale),
            "income": u["monthly_allowance_formatted"],
            "expenses": format_money(total_expenses_minor, currency, locale),
            "tx_count": len(expense_txs),
            "savings": format_money(savings_minor, currency, locale),
            "goal_count": len(goals),
        },
        "chart_data": chart_data,
        "recent_transactions": tx_dicts[:5],
        "monthly_summary": monthly_summary,
        "insights": insights,
    }


def build_before_you_spend_context(db: Session, user: User) -> dict[str, Any]:
    u = user_view_dict(user)
    txs = get_user_transactions(db, user.id)
    balance_minor = _estimate_balance_minor(user, txs)
    essentials_minor = RIYA_PROFILE["upcoming_essentials_minor"] if user.is_demo else 0
    default_purchase = 119900 if user.is_demo else 0

    sim = compute_before_you_spend(
        balance_minor=balance_minor,
        essentials_minor=essentials_minor,
        purchase_minor=default_purchase,
        days_until_income=u["days_until_income"],
        tight_threshold_minor=u["tight_threshold_minor"],
        currency=u["currency"],
        locale=u["locale"],
    )
    return {
        "user": u,
        "active_nav": "before_you_spend",
        "sim": sim,
        "default_item": "JBL Go Portable Speaker" if user.is_demo else "New Purchase",
        "currencies": get_currency_list(),
    }


def build_money_buddy_context(db: Session, user: User) -> dict[str, Any]:
    u = user_view_dict(user)
    currency = u["currency"]
    locale = u["locale"]
    txs = get_user_transactions(db, user.id)
    total_spent = sum(t.amount_minor for t in txs if t.type != "income")
    save_chip_amount = format_money(100000, currency, locale)

    chips = [
        {
            "id": "top-spend",
            "label": "Where am I spending most of my money?",
            "answer": (
                f"Your recorded expenses total {format_money(total_spent, currency, locale)} across {len(txs)} transactions. "
                + ("Food & Mess leads your spending this month." if txs else "Add expenses to see your top category here.")
            ),
            "next_step": "Check your Budgets tab to compare category caps against actual spend.",
            "why": [
                f"Total tracked expenses: {format_money(total_spent, currency, locale)}",
                f"Transactions logged: {len(txs)}",
                f"Monthly allowance: {u['monthly_allowance_formatted']}",
            ],
        },
        {
            "id": "save-target",
            "label": f"How can I save {save_chip_amount} this month?",
            "answer": f"Holding daily non-essential spend steady over the next {u['days_until_income']} days protects your buffer.",
            "next_step": "Move a small weekly amount into Goals right after receiving your allowance.",
            "why": [
                f"Days until next income: {u['days_until_income']}",
                f"Target savings check: {save_chip_amount}",
            ],
        },
        {
            "id": "food-check",
            "label": "Am I spending too much on food?",
            "answer": "Food & Mess spending is tracked directly against your monthly Food & Mess budget.",
            "next_step": "Compare delivery orders vs fixed mess/grocery spend on the Expenses page.",
            "why": [f"Currency: {currency}", f"Logged entries: {len(txs)}"],
        },
        {
            "id": "summarise",
            "label": "Summarise my spending.",
            "answer": f"You have logged {format_money(total_spent, currency, locale)} across {len(txs)} entries against an allowance of {u['monthly_allowance_formatted']}.",
            "next_step": "Run any upcoming purchase through Before You Spend before paying.",
            "why": [
                f"Allowance: {u['monthly_allowance_formatted']}",
                f"Spent to date: {format_money(total_spent, currency, locale)}",
            ],
        },
        {
            "id": "improve-budget",
            "label": "How can I improve my budget?",
            "answer": "Keep recurring essentials covered first, then cap discretionary categories based on your remaining days.",
            "next_step": "Review your category progress bars on the Budgets page.",
            "why": [f"Working currency: {currency}", f"Comfort floor: {u['tight_threshold_formatted']}/day"],
        },
    ]

    return {
        "user": u,
        "active_nav": "money_buddy",
        "chips": chips,
        "initial_entry": chips[0],
    }


def build_expenses_context(db: Session, user: User) -> dict[str, Any]:
    u = user_view_dict(user)
    currency = u["currency"]
    locale = u["locale"]
    txs = get_user_transactions(db, user.id)

    expenses = [
        {
            "id": t.id,
            "date": t.date.isoformat(),
            "merchant": t.merchant,
            "note": t.description,
            "category": t.category,
            "method": t.method,
            "amount_minor": t.amount_minor,
            "amount_formatted": format_money(t.amount_minor, currency, locale),
        }
        for t in txs
    ]
    total_minor = sum(t.amount_minor for t in txs)
    return {
        "user": u,
        "active_nav": "expenses",
        "categories": CATEGORIES,
        "expenses": expenses,
        "total_formatted": format_money(total_minor, currency, locale),
        "count": len(expenses),
    }


def build_budgets_context(db: Session, user: User) -> dict[str, Any]:
    u = user_view_dict(user)
    currency = u["currency"]
    locale = u["locale"]
    budgets = get_user_budgets(db, user.id)
    txs = get_user_transactions(db, user.id)

    spent_by_cat: dict[str, int] = {}
    for t in txs:
        if t.type != "income":
            spent_by_cat[t.category] = spent_by_cat.get(t.category, 0) + t.amount_minor

    items = []
    total_limit = 0
    total_spent = 0
    for b in budgets:
        limit_m = b.limit_minor
        spent_m = spent_by_cat.get(b.category, 0)
        remaining_m = limit_m - spent_m
        pct = int((Decimal(spent_m) / Decimal(limit_m) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if limit_m > 0 else 0
        if pct >= 100:
            tone = "danger"
            status_label = "Over limit"
        elif pct >= 80:
            tone = "warn"
            status_label = "Near limit"
        else:
            tone = "ok"
            status_label = "On track"
        total_limit += limit_m
        total_spent += spent_m
        items.append(
            {
                "category": b.category,
                "limit_minor": limit_m,
                "spent_minor": spent_m,
                "remaining_minor": remaining_m,
                "pct": min(pct, 100),
                "raw_pct": pct,
                "tone": tone,
                "status_label": status_label,
                "limit_formatted": format_money(limit_m, currency, locale),
                "spent_formatted": format_money(spent_m, currency, locale),
                "remaining_formatted": format_money(max(remaining_m, 0), currency, locale),
            }
        )

    total_pct = int((Decimal(total_spent) / Decimal(total_limit) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if total_limit > 0 else 0
    return {
        "user": u,
        "active_nav": "budgets",
        "budgets": items,
        "total_limit_formatted": format_money(total_limit, currency, locale),
        "total_spent_formatted": format_money(total_spent, currency, locale),
        "total_remaining_formatted": format_money(max(total_limit - total_spent, 0), currency, locale),
        "total_pct": min(total_pct, 100),
    }


def build_goals_context(db: Session, user: User) -> dict[str, Any]:
    u = user_view_dict(user)
    currency = u["currency"]
    locale = u["locale"]
    goals_rows = get_user_goals(db, user.id)

    goals = []
    total_saved = 0
    total_target = 0
    for g in goals_rows:
        saved_m = g.saved_minor
        target_m = g.target_minor
        remaining_m = max(target_m - saved_m, 0)
        pct = int((Decimal(saved_m) / Decimal(target_m) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if target_m > 0 else 0
        total_saved += saved_m
        total_target += target_m
        goals.append(
            {
                "id": g.id,
                "title": g.title,
                "note": g.note,
                "deadline": g.deadline.isoformat() if g.deadline else "Flexible",
                "pct": min(pct, 100),
                "saved_formatted": format_money(saved_m, currency, locale),
                "target_formatted": format_money(target_m, currency, locale),
                "remaining_formatted": format_money(remaining_m, currency, locale),
            }
        )

    return {
        "user": u,
        "active_nav": "goals",
        "goals": goals,
        "total_saved_formatted": format_money(total_saved, currency, locale),
        "total_target_formatted": format_money(total_target, currency, locale),
    }


def build_profile_context(user: User, **messages: Any) -> dict[str, Any]:
    u = user_view_dict(user)
    catalog = load_currency_catalog()
    currency_meta = catalog.get("currencies", {}).get(u["currency"], {})
    return {
        "user": u,
        "active_nav": "profile",
        "currency_display": f"{u['currency']} ({currency_meta.get('symbol', u['currency'])}) — {currency_meta.get('name', u['currency'])}",
        "rates_as_of": catalog.get("as_of", "2026-11-01"),
        **messages,
    }
