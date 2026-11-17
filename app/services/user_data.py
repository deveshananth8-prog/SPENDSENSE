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
from app.services.ai_client import (
    _offline_home_narrative,
    _offline_money_buddy,
    is_ai_configured,
)
from app.services.avatars import delete_avatar_file
from app.services.money import (
    convert_minor_amount,
    format_money,
    get_currency_list,
    load_currency_catalog,
    minor_to_decimal,
)
from app.services.snapshot import build_financial_snapshot
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


def _demo_scaled_minor(inr_minor: int, currency_code: str) -> int:
    return convert_minor_amount(inr_minor, "INR", currency_code or "INR")


def _estimate_balance_minor(user: User, transactions: list[Transaction]) -> int:
    income_tx = sum(t.amount_minor for t in transactions if t.type == "income")
    expense_tx = sum(t.amount_minor for t in transactions if t.type != "income")
    if user.is_demo:
        base_bal = _demo_scaled_minor(RIYA_PROFILE["current_balance_minor"], user.currency_code)
        base_exp = _demo_scaled_minor(373700, user.currency_code)
        return max(base_bal + income_tx - max(expense_tx - base_exp, 0), 0)
    return user.monthly_allowance_minor + income_tx - expense_tx


def _currency_symbol(currency_code: str) -> str:
    catalog = load_currency_catalog().get("currencies", {})
    meta = catalog.get((currency_code or "INR").upper())
    return meta["symbol"] if meta else currency_code


def _save_chip_minor(currency_code: str) -> int:
    catalog = load_currency_catalog().get("currencies", {})
    meta = catalog.get((currency_code or "INR").upper())
    rate = Decimal(str(meta.get("rate_from_inr", "1"))) if meta else Decimal("1")
    inr_1000 = Decimal("1000") * rate
    if inr_1000 >= Decimal("500"):
        major = int((inr_1000 / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) * 100
    elif inr_1000 >= Decimal("50"):
        major = int((inr_1000 / Decimal("10")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) * 10
    else:
        major = max(int((inr_1000 / Decimal("5")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) * 5, 5)
    from babel.numbers import get_currency_precision

    precision = get_currency_precision(currency_code)
    return major * (10 ** precision)


def build_home_context(db: Session, user: User) -> dict[str, Any]:
    u = user_view_dict(user)
    currency = u["currency"]
    locale = u["locale"]

    txs = get_user_transactions(db, user.id)
    goals = get_user_goals(db, user.id)

    expense_txs = [t for t in txs if t.type != "income"]
    total_expenses_minor = sum(t.amount_minor for t in expense_txs)
    balance_minor = _estimate_balance_minor(user, txs)
    essentials_minor = _demo_scaled_minor(RIYA_PROFILE["upcoming_essentials_minor"], currency) if user.is_demo else 0
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
            "amount_formatted": format_money(
                t.amount_minor,
                t.currency_code or currency,
                _locale_for_currency(t.currency_code or currency),
            ),
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
        "values_major": [float(minor_to_decimal(c[1], currency)) for c in sorted_cats] if sorted_cats else [1],
        "formatted": [format_money(c[1], currency, locale) for c in sorted_cats] if sorted_cats else [format_money(0, currency, locale)],
    }

    snapshot = build_financial_snapshot(db, user)
    narrative = _offline_home_narrative(snapshot)

    return {
        "user": u,
        "active_nav": "home",
        "runway": runway,
        "kpis": {
            "balance": format_money(balance_minor, currency, locale),
            "balance_minor": balance_minor,
            "essentials_formatted": format_money(essentials_minor, currency, locale),
            "income": u["monthly_allowance_formatted"],
            "income_minor": user.monthly_allowance_minor,
            "expenses": format_money(total_expenses_minor, currency, locale),
            "expenses_minor": total_expenses_minor,
            "tx_count": len(expense_txs),
            "savings": format_money(savings_minor, currency, locale),
            "savings_minor": savings_minor,
            "goal_count": len(goals),
        },
        "chart_data": chart_data,
        "recent_transactions": tx_dicts[:5],
        "monthly_summary": narrative.monthly_summary,
        "insights": narrative.insights,
        "offline_mode": not is_ai_configured(),
    }


def build_before_you_spend_context(db: Session, user: User) -> dict[str, Any]:
    u = user_view_dict(user)
    currency = u["currency"]
    locale = u["locale"]
    txs = get_user_transactions(db, user.id)
    expense_txs = [t for t in txs if t.type != "income"]
    balance_minor = _estimate_balance_minor(user, txs)
    essentials_minor = _demo_scaled_minor(RIYA_PROFILE["upcoming_essentials_minor"], currency) if user.is_demo else 0
    if user.is_demo:
        default_purchase = _demo_scaled_minor(119900, currency)
    elif balance_minor > 0:
        default_purchase = max(balance_minor // 5, 1)
    else:
        default_purchase = 0

    sim = compute_before_you_spend(
        balance_minor=balance_minor,
        essentials_minor=essentials_minor,
        purchase_minor=default_purchase,
        days_until_income=u["days_until_income"],
        tight_threshold_minor=u["tight_threshold_minor"],
        currency=currency,
        locale=locale,
    )

    tx_for_runway = [{"amount_minor": t.amount_minor, "essential": t.essential} for t in expense_txs]
    runway_before = compute_runway(
        balance_minor=balance_minor,
        essentials_minor=essentials_minor,
        days_until_income=u["days_until_income"],
        expenses=tx_for_runway,
        today=date.today(),
        currency=currency,
        locale=locale,
    )
    runway_after = compute_runway(
        balance_minor=max(balance_minor - default_purchase, 0),
        essentials_minor=essentials_minor,
        days_until_income=u["days_until_income"],
        expenses=tx_for_runway,
        today=date.today(),
        currency=currency,
        locale=locale,
    )

    def _major_str(minor: int) -> str:
        val = minor_to_decimal(minor, currency)
        if val == val.to_integral_value():
            return str(int(val))
        return format(val, "f").rstrip("0").rstrip(".")

    return {
        "user": u,
        "active_nav": "before_you_spend",
        "sim": sim,
        "runway_before": runway_before,
        "runway_after": runway_after,
        "avg_daily_spend_minor": runway_before["avg_daily_spend_minor"],
        "default_item": "JBL Go Portable Speaker" if user.is_demo else "New Purchase",
        "currency_symbol": _currency_symbol(currency),
        "defaults": {
            "purchase": _major_str(default_purchase),
            "balance": _major_str(balance_minor),
            "essentials": _major_str(essentials_minor),
            "days": str(u["days_until_income"]),
            "threshold": _major_str(u["tight_threshold_minor"]),
        },
        "currencies": get_currency_list(),
        "offline_mode": not is_ai_configured(),
    }


def build_money_buddy_context(db: Session, user: User) -> dict[str, Any]:
    u = user_view_dict(user)
    currency = u["currency"]
    locale = u["locale"]
    snapshot = build_financial_snapshot(db, user)
    save_chip_amount = format_money(_save_chip_minor(currency), currency, locale)

    chip_specs = [
        ("top-spend", "Where am I spending most of my money?"),
        ("save-target", f"How can I save {save_chip_amount} this month?"),
        ("food-check", "Am I spending too much on food?"),
        ("summarise", "Summarise my spending."),
        ("improve-budget", "How can I improve my budget?"),
    ]

    chips = []
    for chip_id, label in chip_specs:
        res = _offline_money_buddy(label, snapshot)
        chips.append(
            {
                "id": chip_id,
                "label": label,
                "answer": res.answer,
                "next_step": res.next_step,
                "why": res.why,
            }
        )

    return {
        "user": u,
        "active_nav": "money_buddy",
        "chips": chips,
        "initial_entry": chips[0],
        "offline_mode": not is_ai_configured(),
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
            "type": t.type,
            "currency": t.currency_code or currency,
            "method": t.method,
            "amount_minor": t.amount_minor,
            "amount_formatted": format_money(
                t.amount_minor,
                t.currency_code or currency,
                _locale_for_currency(t.currency_code or currency),
            ),
        }
        for t in txs
    ]
    total_minor = sum(t.amount_minor for t in txs if t.type != "income")
    return {
        "user": u,
        "active_nav": "expenses",
        "categories": CATEGORIES,
        "currencies": get_currency_list(),
        "currency_symbol": _currency_symbol(currency),
        "today_iso": date.today().isoformat(),
        "expenses": expenses,
        "total_formatted": format_money(total_minor, currency, locale),
        "count": len(expenses),
        "offline_mode": not is_ai_configured(),
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
        "month_label": date.today().strftime("%B %Y"),
        "currency_symbol": _currency_symbol(currency),
        "categories": CATEGORIES,
        "category_count": len(items),
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
        "currency_symbol": _currency_symbol(currency),
        "today_iso": date.today().isoformat(),
        "goals": goals,
        "total_saved_formatted": format_money(total_saved, currency, locale),
        "total_target_formatted": format_money(total_target, currency, locale),
    }


def _major_input_str(amount_minor: int, currency_code: str) -> str:
    val = minor_to_decimal(amount_minor, currency_code)
    if val == val.to_integral_value():
        return str(int(val))
    return format(val, "f").rstrip("0").rstrip(".")


def build_profile_context(user: User, **messages: Any) -> dict[str, Any]:
    u = user_view_dict(user)
    catalog = load_currency_catalog()
    currency_meta = catalog.get("currencies", {}).get(u["currency"], {})
    from babel.numbers import get_currency_precision

    precision = get_currency_precision(u["currency"])
    return {
        "user": u,
        "active_nav": "profile",
        "currency_display": f"{u['currency']} ({currency_meta.get('symbol', u['currency'])}) — {currency_meta.get('name', u['currency'])}",
        "currencies": get_currency_list(),
        "allowance_major": _major_input_str(user.monthly_allowance_minor, u["currency"]),
        "tight_threshold_major": _major_input_str(user.tight_threshold_minor, u["currency"]),
        "currency_precision": precision,
        "rates_as_of": catalog.get("as_of", "2026-11-01"),
        **messages,
    }


def preview_currency_conversion(db: Session, user: User, target_currency: str) -> dict[str, Any]:
    src = (user.currency_code or "INR").upper()
    dst = (target_currency or src).strip().upper()
    catalog = load_currency_catalog()
    currencies = catalog.get("currencies", {})
    if dst not in currencies:
        raise ValueError("Unsupported target currency.")

    src_meta = currencies[src]
    dst_meta = currencies[dst]
    src_locale = src_meta["locale"]
    dst_locale = dst_meta["locale"]

    txs = get_user_transactions(db, user.id)
    budgets = get_user_budgets(db, user.id)
    goals = get_user_goals(db, user.id)

    tx_total_src = sum(t.amount_minor for t in txs if t.type != "income")
    tx_total_dst = sum(convert_minor_amount(t.amount_minor, t.currency_code or src, dst) for t in txs if t.type != "income")

    budget_total_src = sum(b.limit_minor for b in budgets)
    budget_total_dst = sum(convert_minor_amount(b.limit_minor, src, dst) for b in budgets)

    goal_total_src = sum(g.saved_minor for g in goals)
    goal_total_dst = sum(convert_minor_amount(g.saved_minor, src, dst) for g in goals)

    allowance_dst = convert_minor_amount(user.monthly_allowance_minor, src, dst)
    threshold_dst = convert_minor_amount(user.tight_threshold_minor, src, dst)

    src_rate = Decimal(str(src_meta["rate_from_inr"]))
    dst_rate = Decimal(str(dst_meta["rate_from_inr"]))
    cross_rate = (dst_rate / src_rate).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    return {
        "from_currency": src,
        "to_currency": dst,
        "to_symbol": dst_meta["symbol"],
        "to_name": dst_meta["name"],
        "same_currency": src == dst,
        "rate_display": f"1 {src} ≈ {cross_rate} {dst}",
        "as_of": catalog.get("as_of", "2026-11-01"),
        "rows": [
            {
                "label": "Monthly allowance",
                "before": format_money(user.monthly_allowance_minor, src, src_locale),
                "after": format_money(allowance_dst, dst, dst_locale),
            },
            {
                "label": "Daily comfort floor",
                "before": format_money(user.tight_threshold_minor, src, src_locale),
                "after": format_money(threshold_dst, dst, dst_locale),
            },
            {
                "label": f"Expenses ({len([t for t in txs if t.type != 'income'])} entries)",
                "before": format_money(tx_total_src, src, src_locale),
                "after": format_money(tx_total_dst, dst, dst_locale),
            },
            {
                "label": f"Monthly budgets ({len(budgets)})",
                "before": format_money(budget_total_src, src, src_locale),
                "after": format_money(budget_total_dst, dst, dst_locale),
            },
            {
                "label": f"Goals saved ({len(goals)})",
                "before": format_money(goal_total_src, src, src_locale),
                "after": format_money(goal_total_dst, dst, dst_locale),
            },
        ],
    }


def convert_user_currency(db: Session, user: User, target_currency: str) -> User:
    src = (user.currency_code or "INR").upper()
    dst = (target_currency or src).strip().upper()
    catalog = load_currency_catalog().get("currencies", {})
    if dst not in catalog:
        raise ValueError("Unsupported target currency.")
    if src == dst:
        return user

    db_user = db.query(User).filter(User.id == user.id).first()
    if not db_user:
        raise ValueError("User not found.")

    db_user.monthly_allowance_minor = convert_minor_amount(db_user.monthly_allowance_minor, src, dst)
    db_user.tight_threshold_minor = convert_minor_amount(db_user.tight_threshold_minor, src, dst)

    txs = get_user_transactions(db, db_user.id)
    for t in txs:
        t_src = (t.currency_code or src).upper()
        t.amount_minor = max(convert_minor_amount(t.amount_minor, t_src, dst), 1 if t.amount_minor > 0 else 0)
        t.currency_code = dst

    budgets = get_user_budgets(db, db_user.id)
    for b in budgets:
        b.limit_minor = convert_minor_amount(b.limit_minor, src, dst)

    goals = get_user_goals(db, db_user.id)
    for g in goals:
        g.target_minor = max(convert_minor_amount(g.target_minor, src, dst), 1 if g.target_minor > 0 else 0)
        g.saved_minor = convert_minor_amount(g.saved_minor, src, dst)

    db_user.currency_code = dst
    db.commit()
    db.refresh(db_user)
    return db_user

