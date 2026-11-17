"""Grounded financial snapshot builder for Stage 4 AI calls.

Every query filters strictly by user.id so no other user's data can ever enter
an AI prompt or response. All numbers are pre-computed in integer minor units
and formatted via Babel.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from app.models import Budget, Goal, Transaction, User
from app.services.money import format_money, load_currency_catalog
from app.services.stage1_data import compute_runway
from data.sample_data import RIYA_PROFILE


def _locale_for_currency(currency_code: str) -> tuple[str, str]:
    catalog = load_currency_catalog().get("currencies", {})
    meta = catalog.get((currency_code or "INR").upper())
    if meta:
        return meta["locale"], meta["symbol"]
    return "en_US", currency_code or "USD"


def build_financial_snapshot(
    db: Session,
    user: User,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """Build a strictly user-scoped, pre-computed financial snapshot."""
    ref_today = today or date.today()
    currency = (user.currency_code or "INR").upper()
    locale, symbol = _locale_for_currency(currency)

    txs = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .all()
    )
    budgets = (
        db.query(Budget)
        .filter(Budget.user_id == user.id)
        .order_by(Budget.id.asc())
        .all()
    )
    goals = (
        db.query(Goal)
        .filter(Goal.user_id == user.id)
        .order_by(Goal.id.asc())
        .all()
    )

    expense_txs = [t for t in txs if t.type != "income"]
    income_txs = [t for t in txs if t.type == "income"]

    monthly_expenses_minor = sum(t.amount_minor for t in expense_txs)
    extra_income_minor = sum(t.amount_minor for t in income_txs)
    monthly_income_minor = user.monthly_allowance_minor + extra_income_minor

    if user.is_demo:
        # Demo account keeps Riya's baseline balance adjusted by any newly logged transactions
        demo_base_expense_minor = sum(e["amount_minor"] for e in [])  # tracked directly below
        current_balance_minor = max(
            RIYA_PROFILE["current_balance_minor"] + extra_income_minor - max(monthly_expenses_minor - 373700, 0),
            0,
        )
        essentials_minor = RIYA_PROFILE["upcoming_essentials_minor"]
    else:
        current_balance_minor = monthly_income_minor - monthly_expenses_minor
        essentials_minor = 0

    days_until_income = (
        max((user.next_income_date - ref_today).days, 1)
        if user.next_income_date
        else 12
    )

    tx_for_runway = [
        {
            "amount_minor": t.amount_minor,
            "essential": t.essential,
        }
        for t in expense_txs
    ]
    runway = compute_runway(
        balance_minor=current_balance_minor,
        essentials_minor=essentials_minor,
        days_until_income=days_until_income,
        expenses=tx_for_runway,
        today=ref_today,
        currency=currency,
        locale=locale,
    )

    # Category totals
    cat_map: dict[str, int] = {}
    for t in expense_txs:
        cat_map[t.category] = cat_map.get(t.category, 0) + t.amount_minor
    sorted_cats = sorted(cat_map.items(), key=lambda x: x[1], reverse=True)

    category_totals = []
    for cat, amt in sorted_cats:
        share_pct = (
            int((Decimal(amt) / Decimal(monthly_expenses_minor) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            if monthly_expenses_minor > 0
            else 0
        )
        category_totals.append(
            {
                "category": cat,
                "total_minor": amt,
                "total_formatted": format_money(amt, currency, locale),
                "share_pct": share_pct,
            }
        )

    # Budgets used
    budgets_used = []
    for b in budgets:
        spent_m = cat_map.get(b.category, 0)
        limit_m = b.limit_minor
        pct = (
            int((Decimal(spent_m) / Decimal(limit_m) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            if limit_m > 0
            else 0
        )
        status = "Over limit" if pct >= 100 else ("Near limit" if pct >= 80 else "On track")
        budgets_used.append(
            {
                "category": b.category,
                "limit_minor": limit_m,
                "spent_minor": spent_m,
                "pct": pct,
                "status": status,
                "limit_formatted": format_money(limit_m, currency, locale),
                "spent_formatted": format_money(spent_m, currency, locale),
                "remaining_formatted": format_money(max(limit_m - spent_m, 0), currency, locale),
            }
        )

    # Goals progress
    goals_progress = []
    for g in goals:
        pct = (
            int((Decimal(g.saved_minor) / Decimal(g.target_minor) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            if g.target_minor > 0
            else 0
        )
        goals_progress.append(
            {
                "title": g.title,
                "saved_minor": g.saved_minor,
                "target_minor": g.target_minor,
                "pct": min(pct, 100),
                "deadline": g.deadline.isoformat() if g.deadline else "Flexible",
                "saved_formatted": format_money(g.saved_minor, currency, locale),
                "target_formatted": format_money(g.target_minor, currency, locale),
                "remaining_formatted": format_money(max(g.target_minor - g.saved_minor, 0), currency, locale),
            }
        )

    # Computed insights (strictly from real user numbers, zero invented figures)
    computed_insights: list[dict[str, Any]] = []
    if category_totals:
        top_cat = category_totals[0]
        computed_insights.append(
            {
                "id": "top-category",
                "title": f"Top category: {top_cat['category']}",
                "metric": f"{top_cat['share_pct']}% of spend",
                "tone": "warn" if top_cat["share_pct"] >= 45 else "ok",
                "fact": (
                    f"{top_cat['category']} accounts for {top_cat['total_formatted']} "
                    f"({top_cat['share_pct']}% of your {format_money(monthly_expenses_minor, currency, locale)} total)."
                ),
                "buddy_question": f"Why is {top_cat['category']} my biggest expense and how can I trim it?",
            }
        )
    else:
        computed_insights.append(
            {
                "id": "no-expenses",
                "title": "Ready to track",
                "metric": format_money(0, currency, locale),
                "tone": "ok",
                "fact": (
                    f"You have {format_money(monthly_income_minor, currency, locale)} logged for income/allowance "
                    f"and {days_until_income} days until your next income."
                ),
                "buddy_question": "How should I set up my monthly budgets?",
            }
        )

    warm_budgets = [b for b in budgets_used if b["pct"] >= 80]
    if warm_budgets:
        wb = sorted(warm_budgets, key=lambda x: x["pct"], reverse=True)[0]
        computed_insights.append(
            {
                "id": "budget-watch",
                "title": f"{wb['category']} budget at {wb['pct']}%",
                "metric": f"{wb['remaining_formatted']} left",
                "tone": "danger" if wb["pct"] >= 100 else "warn",
                "fact": (
                    f"You've used {wb['spent_formatted']} of your {wb['limit_formatted']} {wb['category']} budget "
                    f"with {days_until_income} days left until next income."
                ),
                "buddy_question": f"Am I spending too much on {wb['category']}?",
            }
        )
    else:
        computed_insights.append(
            {
                "id": "runway-pace",
                "title": f"Runway status: {runway['status']}",
                "metric": f"{runway['formatted']['max_per_day']}/day cap",
                "tone": runway["status_tone"],
                "fact": (
                    f"Your 14-day average is {runway['formatted']['avg_daily_spend']}/day against a "
                    f"{runway['formatted']['max_per_day']}/day comfort cap for the next {days_until_income} days."
                ),
                "buddy_question": "How can I make my money last past next income?",
            }
        )

    last_10_transactions = [
        {
            "date": t.date.isoformat(),
            "merchant": t.merchant,
            "category": t.category,
            "description": t.description,
            "amount_minor": t.amount_minor,
            "amount_formatted": format_money(t.amount_minor, currency, locale),
            "type": t.type,
            "method": t.method,
        }
        for t in txs[:10]
    ]

    snapshot_facts = [
        f"Working currency: {currency} ({symbol})",
        f"Current balance: {format_money(current_balance_minor, currency, locale)}",
        f"Upcoming essentials reserved: {format_money(essentials_minor, currency, locale)}",
        f"Monthly allowance & income: {format_money(monthly_income_minor, currency, locale)}",
        f"Monthly expenses ({len(expense_txs)} entries): {format_money(monthly_expenses_minor, currency, locale)}",
        f"Runway status: {runway['status']} ({runway['runway_days']} days vs {days_until_income} days to next income)",
        f"Safe daily cap: {runway['formatted']['max_per_day']}/day (14-day avg: {runway['formatted']['avg_daily_spend']}/day)",
    ]
    if category_totals:
        snapshot_facts.append(
            f"Top category: {category_totals[0]['category']} at {category_totals[0]['total_formatted']} ({category_totals[0]['share_pct']}%)"
        )
    if goals_progress:
        total_goal_saved = sum(g["saved_minor"] for g in goals_progress)
        snapshot_facts.append(
            f"Saved across {len(goals_progress)} goals: {format_money(total_goal_saved, currency, locale)}"
        )

    return {
        "user_currency": currency,
        "user_locale": locale,
        "currency_symbol": symbol,
        "days_until_income": days_until_income,
        "monthly_allowance_minor": user.monthly_allowance_minor,
        "monthly_allowance_formatted": format_money(user.monthly_allowance_minor, currency, locale),
        "monthly_income_minor": monthly_income_minor,
        "monthly_income_formatted": format_money(monthly_income_minor, currency, locale),
        "monthly_expenses_minor": monthly_expenses_minor,
        "monthly_expenses_formatted": format_money(monthly_expenses_minor, currency, locale),
        "current_balance_minor": current_balance_minor,
        "current_balance_formatted": format_money(current_balance_minor, currency, locale),
        "upcoming_essentials_minor": essentials_minor,
        "upcoming_essentials_formatted": format_money(essentials_minor, currency, locale),
        "transaction_count": len(txs),
        "category_totals": category_totals,
        "runway": {
            "status": runway["status"],
            "status_tone": runway["status_tone"],
            "headline": runway["headline"],
            "runway_days": runway["runway_days"],
            "days_until_income": runway["days_until_income"],
            "safe_balance_formatted": runway["formatted"]["safe_balance"],
            "avg_daily_spend_formatted": runway["formatted"]["avg_daily_spend"],
            "max_per_day_formatted": runway["formatted"]["max_per_day"],
            "run_out_str": runway["run_out_str"],
            "next_income_str": runway["next_income_str"],
        },
        "budgets_used": budgets_used,
        "goals_progress": goals_progress,
        "computed_insights": computed_insights,
        "last_10_transactions": last_10_transactions,
        "snapshot_facts": snapshot_facts,
    }
