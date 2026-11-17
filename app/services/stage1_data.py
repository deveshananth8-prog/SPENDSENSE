"""Stage 1 pure calculation & sample view-model assembly for SpendSense AI.

Uses Decimal and integer minor units strictly — zero floats for money.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.services.money import format_money, get_currency_list, load_currency_catalog
from data.sample_data import (
    CATEGORIES,
    RIYA_BUDGETS,
    RIYA_EXPENSES,
    RIYA_GOALS,
    RIYA_PROFILE,
)


def _round_minor(val: Decimal) -> int:
    return int(val.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def compute_before_you_spend(
    *,
    balance_minor: int,
    essentials_minor: int,
    purchase_minor: int,
    days_until_income: int,
    tight_threshold_minor: int,
    currency: str = "INR",
    locale: str = "en_IN",
) -> dict[str, Any]:
    days = max(int(days_until_income), 1)
    safe_to_spend = balance_minor - essentials_minor
    left_after_buying = safe_to_spend - purchase_minor
    daily_after = _round_minor(Decimal(left_after_buying) / Decimal(days))
    daily_before = _round_minor(Decimal(safe_to_spend) / Decimal(days))

    if left_after_buying < 0:
        verdict = "Not now"
        verdict_tone = "danger"
        verdict_summary = "This purchase dips into money set aside for upcoming essentials."
    elif daily_after < tight_threshold_minor:
        verdict = "Tight"
        verdict_tone = "warn"
        verdict_summary = (
            f"You can buy it, but your daily buffer drops below {format_money(tight_threshold_minor, currency, locale)}/day."
        )
    else:
        verdict = "Comfortable"
        verdict_tone = "ok"
        verdict_summary = "You stay well above your daily comfort floor until your next allowance."

    # Alternative 1: Wait N days (smallest N where skipping daily non-essential spend or waiting until next allowance works)
    # Using daily allowance recovery: if you wait N days (saving tight_threshold/day or until next income day),
    # let's find smallest N in 1..days where remaining days after N keeps daily_after >= tight_threshold,
    # or if unreachable before payday, suggest waiting until next allowance (days days).
    wait_days = 0
    if verdict != "Comfortable":
        found = None
        for n in range(1, days):
            remaining_days = max(days - n, 1)
            candidate_daily = _round_minor(Decimal(left_after_buying) / Decimal(remaining_days))
            if left_after_buying >= 0 and candidate_daily >= tight_threshold_minor:
                found = n
                break
        wait_days = found if found is not None else days

    # Alternative 2: Cheaper option (highest price keeping daily_after >= tight_threshold_minor)
    min_needed_after = tight_threshold_minor * days
    cheaper_max_minor = max(safe_to_spend - min_needed_after, 0)

    # Alternative 3: Split into two payments
    first_payment_minor = purchase_minor // 2
    second_payment_minor = purchase_minor - first_payment_minor
    left_after_first = safe_to_spend - first_payment_minor
    daily_after_first = _round_minor(Decimal(left_after_first) / Decimal(days))

    return {
        "balance_minor": balance_minor,
        "essentials_minor": essentials_minor,
        "purchase_minor": purchase_minor,
        "days": days,
        "tight_threshold_minor": tight_threshold_minor,
        "safe_to_spend_minor": safe_to_spend,
        "left_after_buying_minor": left_after_buying,
        "daily_before_minor": daily_before,
        "daily_after_minor": daily_after,
        "verdict": verdict,
        "verdict_tone": verdict_tone,
        "verdict_summary": verdict_summary,
        "wait_days": wait_days,
        "wait_until_income": wait_days >= days and verdict != "Comfortable",
        "cheaper_max_minor": cheaper_max_minor,
        "first_payment_minor": first_payment_minor,
        "second_payment_minor": second_payment_minor,
        "daily_after_first_minor": daily_after_first,
        "formatted": {
            "balance": format_money(balance_minor, currency, locale),
            "essentials": format_money(essentials_minor, currency, locale),
            "purchase": format_money(purchase_minor, currency, locale),
            "safe_to_spend": format_money(safe_to_spend, currency, locale),
            "left_after_buying": format_money(left_after_buying, currency, locale),
            "daily_before": format_money(daily_before, currency, locale),
            "daily_after": format_money(daily_after, currency, locale),
            "tight_threshold": format_money(tight_threshold_minor, currency, locale),
            "cheaper_max": format_money(cheaper_max_minor, currency, locale),
            "first_payment": format_money(first_payment_minor, currency, locale),
            "second_payment": format_money(second_payment_minor, currency, locale),
            "daily_after_first": format_money(daily_after_first, currency, locale),
        },
    }


def compute_runway(
    *,
    balance_minor: int,
    essentials_minor: int,
    days_until_income: int,
    expenses: list[dict[str, Any]],
    today: date | None = None,
    currency: str = "INR",
    locale: str = "en_IN",
) -> dict[str, Any]:
    ref_today = today or date(2026, 11, 17)
    days = max(int(days_until_income), 1)
    next_income_date = ref_today + timedelta(days=days)

    safe_balance = max(balance_minor - essentials_minor, 0)
    non_essential_14d = sum(e["amount_minor"] for e in expenses if not e.get("essential", False))
    avg_daily_spend = max(_round_minor(Decimal(non_essential_14d) / Decimal(14)), 100)

    runway_days_dec = Decimal(safe_balance) / Decimal(avg_daily_spend)
    runway_days = int(runway_days_dec.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    run_out_date = ref_today + timedelta(days=runway_days)

    if run_out_date >= next_income_date:
        status = "Safe"
        status_tone = "ok"
        cushion_days = (run_out_date - next_income_date).days
        headline = f"Your money lasts {cushion_days} days past next allowance"
    elif (next_income_date - run_out_date).days <= 3:
        status = "Watch"
        status_tone = "warn"
        short_days = (next_income_date - run_out_date).days
        headline = f"Runs out {short_days} day(s) before next allowance"
    else:
        status = "At risk"
        status_tone = "danger"
        short_days = (next_income_date - run_out_date).days
        headline = f"Projected to run short {short_days} days early"

    max_per_day = _round_minor(Decimal(safe_balance) / Decimal(days))

    # Timeline marker percentages along a 0..total_span scale
    span_days = max(days + 6, runway_days + 2, 16)
    income_pct = min(max(int((Decimal(days) / Decimal(span_days)) * 100), 15), 92)
    runout_pct = min(max(int((Decimal(runway_days) / Decimal(span_days)) * 100), 8), 96)

    return {
        "status": status,
        "status_tone": status_tone,
        "headline": headline,
        "safe_balance_minor": safe_balance,
        "avg_daily_spend_minor": avg_daily_spend,
        "runway_days": runway_days,
        "days_until_income": days,
        "today_str": ref_today.strftime("%d %b"),
        "next_income_str": next_income_date.strftime("%d %b"),
        "run_out_str": run_out_date.strftime("%d %b"),
        "max_per_day_minor": max_per_day,
        "income_pct": income_pct,
        "runout_pct": runout_pct,
        "formatted": {
            "safe_balance": format_money(safe_balance, currency, locale),
            "avg_daily_spend": format_money(avg_daily_spend, currency, locale),
            "max_per_day": format_money(max_per_day, currency, locale),
        },
    }


def get_base_user() -> dict[str, Any]:
    currency = RIYA_PROFILE["currency"]
    locale = RIYA_PROFILE["locale"]
    return {
        **RIYA_PROFILE,
        "monthly_allowance_formatted": format_money(RIYA_PROFILE["monthly_allowance_minor"], currency, locale),
        "current_balance_formatted": format_money(RIYA_PROFILE["current_balance_minor"], currency, locale),
        "upcoming_essentials_formatted": format_money(RIYA_PROFILE["upcoming_essentials_minor"], currency, locale),
        "tight_threshold_formatted": format_money(RIYA_PROFILE["tight_threshold_minor"], currency, locale),
    }


def get_home_context() -> dict[str, Any]:
    user = get_base_user()
    currency = user["currency"]
    locale = user["locale"]

    total_expenses_minor = sum(e["amount_minor"] for e in RIYA_EXPENSES)
    income_minor = user["monthly_allowance_minor"]
    savings_minor = sum(g["saved_minor"] for g in RIYA_GOALS)

    runway = compute_runway(
        balance_minor=user["current_balance_minor"],
        essentials_minor=user["upcoming_essentials_minor"],
        days_until_income=user["days_until_income"],
        expenses=RIYA_EXPENSES,
        currency=currency,
        locale=locale,
    )

    # Category totals for the single spending breakdown chart
    cat_totals: dict[str, int] = {}
    for exp in RIYA_EXPENSES:
        cat_totals[exp["category"]] = cat_totals.get(exp["category"], 0) + exp["amount_minor"]
    sorted_cats = sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)

    chart_data = {
        "labels": [c[0] for c in sorted_cats],
        "values_major": [float(Decimal(c[1]) / Decimal(100)) for c in sorted_cats],
        "formatted": [format_money(c[1], currency, locale) for c in sorted_cats],
    }

    recent_transactions = [
        {
            **exp,
            "amount_formatted": format_money(exp["amount_minor"], currency, locale),
        }
        for exp in RIYA_EXPENSES[:5]
    ]

    insights = [
        {
            "title": "Weekend spend runs 1.6x higher",
            "metric": "1.6x ratio",
            "body": (
                f"Your weekend outings and late-night Zomato orders average {format_money(31250, currency, locale)} "
                f"per weekend vs {format_money(9629, currency, locale)}/day on weekdays."
            ),
            "tone": "warn",
        },
        {
            "title": "Most frequent small spend: Evening chai",
            "metric": f"{format_money(4000, currency, locale)} each",
            "body": (
                f"Small tap-and-pay chai and snack trips stay well under budget, and cutting just two food delivery "
                f"orders frees {format_money(43000, currency, locale)} toward your headphones goal."
            ),
            "tone": "ok",
        },
    ]

    return {
        "user": user,
        "active_nav": "home",
        "runway": runway,
        "kpis": {
            "balance": format_money(user["current_balance_minor"], currency, locale),
            "income": format_money(income_minor, currency, locale),
            "expenses": format_money(total_expenses_minor, currency, locale),
            "savings": format_money(savings_minor, currency, locale),
        },
        "chart_data": chart_data,
        "recent_transactions": recent_transactions,
        "monthly_summary": (
            f"You have spent {format_money(total_expenses_minor, currency, locale)} of your "
            f"{format_money(income_minor, currency, locale)} November allowance. Food & Mess accounts for "
            f"half of your outflow, and after setting aside {format_money(user['upcoming_essentials_minor'], currency, locale)} "
            f"for hostel essentials, you can spend up to {runway['formatted']['max_per_day']} a day without dipping early."
        ),
        "insights": insights,
    }


def get_before_you_spend_context() -> dict[str, Any]:
    user = get_base_user()
    currency = user["currency"]
    locale = user["locale"]
    # Default scenario: ₹1,199 Bluetooth speaker / hostel desk lamp
    default_purchase = 119900
    sim = compute_before_you_spend(
        balance_minor=user["current_balance_minor"],
        essentials_minor=user["upcoming_essentials_minor"],
        purchase_minor=default_purchase,
        days_until_income=user["days_until_income"],
        tight_threshold_minor=user["tight_threshold_minor"],
        currency=currency,
        locale=locale,
    )
    return {
        "user": user,
        "active_nav": "before_you_spend",
        "sim": sim,
        "default_item": "JBL Go Portable Speaker",
        "currencies": get_currency_list(),
    }


def get_money_buddy_context() -> dict[str, Any]:
    user = get_base_user()
    currency = user["currency"]
    locale = user["locale"]
    save_chip_amount = format_money(100000, currency, locale)  # ₹1,000.00

    chips = [
        {
            "id": "top-spend",
            "label": "Where am I spending most of my money?",
            "answer": (
                f"Food & Mess is your biggest category this month at {format_money(191500, currency, locale)} "
                f"(about 51% of total spend), led by your monthly hostel mess coupon ({format_money(145000, currency, locale)}) "
                f"and two delivery orders ({format_money(43000, currency, locale)})."
            ),
            "next_step": "Cook or eat at the mess on weeknights for the next 10 days to keep ₹400+ in your buffer.",
            "why": [
                f"Food & Mess total: {format_money(191500, currency, locale)}",
                f"Total November expenses: {format_money(373700, currency, locale)}",
                f"Entertainment (2nd highest): {format_money(43900, currency, locale)}",
                f"Safe-to-spend remaining: {format_money(163000, currency, locale)}",
            ],
        },
        {
            "id": "save-target",
            "label": f"How can I save {save_chip_amount} this month?",
            "answer": (
                f"To keep {save_chip_amount} by November 29, hold your daily non-essential spending to "
                f"{format_money(5250, currency, locale)}/day instead of your current {format_money(9629, currency, locale)}/day. "
                f"Skipping two delivery orders and one weekend outing gets you 80% of the way there."
            ),
            "next_step": f"Move {format_money(50000, currency, locale)} into your Semester Break Train goal right after your next allowance.",
            "why": [
                f"Safe-to-spend balance: {format_money(163000, currency, locale)}",
                f"Target leftover buffer: {format_money(100000, currency, locale)}",
                f"Available spend for 12 days: {format_money(63000, currency, locale)}",
                f"Current 14-day daily average: {format_money(9629, currency, locale)}",
            ],
        },
        {
            "id": "food-check",
            "label": "Am I spending too much on food?",
            "answer": (
                f"Your fixed mess fee ({format_money(145000, currency, locale)}) is sensible, and you still have "
                f"{format_money(28500, currency, locale)} left in your {format_money(220000, currency, locale)} Food & Mess budget. "
                f"The main leak is late-night delivery, which added {format_money(43000, currency, locale)} across two orders."
            ),
            "next_step": "Set a soft cap of one Swiggy/Zomato order per week until exams wrap up.",
            "why": [
                f"Food & Mess spent: {format_money(191500, currency, locale)}",
                f"Food & Mess budget limit: {format_money(220000, currency, locale)}",
                f"Zomato + Swiggy combined: {format_money(43000, currency, locale)}",
                f"Budget usage: 87% with 12 days left",
            ],
        },
        {
            "id": "summarise",
            "label": "Summarise my spending.",
            "answer": (
                f"So far in November you've spent {format_money(373700, currency, locale)} across 12 transactions, "
                f"leaving {format_money(248000, currency, locale)} in your account ({format_money(163000, currency, locale)} after "
                f"setting aside {format_money(85000, currency, locale)} for upcoming essentials). Your runway is Safe at 17 days."
            ),
            "next_step": "Run any purchase above ₹300 through Before You Spend before tapping pay.",
            "why": [
                f"Monthly allowance: {format_money(600000, currency, locale)}",
                f"Spent to date: {format_money(373700, currency, locale)}",
                f"Upcoming essentials: {format_money(85000, currency, locale)}",
                "Runway status: Safe (17 days vs 12 days to payday)",
            ],
        },
        {
            "id": "improve-budget",
            "label": "How can I improve my budget?",
            "answer": (
                f"Food & Mess (87% used) and Entertainment (88% used) are running warm with 12 days remaining, "
                f"while Education ({format_money(14000, currency, locale)} of {format_money(40000, currency, locale)}) has plenty of room."
            ),
            "next_step": f"Shift {format_money(15000, currency, locale)} of unused Other/Education headroom into Food & Mess next month.",
            "why": [
                f"Food & Mess used: {format_money(191500, currency, locale)} / {format_money(220000, currency, locale)}",
                f"Entertainment used: {format_money(43900, currency, locale)} / {format_money(50000, currency, locale)}",
                f"Education used: {format_money(14000, currency, locale)} / {format_money(40000, currency, locale)}",
                f"Other used: {format_money(0, currency, locale)} / {format_money(20000, currency, locale)}",
            ],
        },
    ]

    return {
        "user": user,
        "active_nav": "money_buddy",
        "chips": chips,
        "initial_entry": chips[0],
    }


def get_expenses_context() -> dict[str, Any]:
    user = get_base_user()
    currency = user["currency"]
    locale = user["locale"]

    expenses = [
        {
            **e,
            "amount_formatted": format_money(e["amount_minor"], currency, locale),
            "amount_major_str": f"{Decimal(e['amount_minor']) / Decimal(100):.2f}",
        }
        for e in RIYA_EXPENSES
    ]
    total_minor = sum(e["amount_minor"] for e in RIYA_EXPENSES)
    return {
        "user": user,
        "active_nav": "expenses",
        "categories": CATEGORIES,
        "expenses": expenses,
        "total_formatted": format_money(total_minor, currency, locale),
        "count": len(expenses),
    }


def get_budgets_context() -> dict[str, Any]:
    user = get_base_user()
    currency = user["currency"]
    locale = user["locale"]

    items = []
    total_limit = 0
    total_spent = 0
    for b in RIYA_BUDGETS:
        limit_m = b["limit_minor"]
        spent_m = b["spent_minor"]
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
                "category": b["category"],
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

    return {
        "user": user,
        "active_nav": "budgets",
        "budgets": items,
        "total_limit_formatted": format_money(total_limit, currency, locale),
        "total_spent_formatted": format_money(total_spent, currency, locale),
        "total_remaining_formatted": format_money(max(total_limit - total_spent, 0), currency, locale),
        "total_pct": int((Decimal(total_spent) / Decimal(total_limit) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
    }


def get_goals_context() -> dict[str, Any]:
    user = get_base_user()
    currency = user["currency"]
    locale = user["locale"]

    goals = []
    total_saved = 0
    total_target = 0
    for g in RIYA_GOALS:
        saved_m = g["saved_minor"]
        target_m = g["target_minor"]
        remaining_m = max(target_m - saved_m, 0)
        pct = int((Decimal(saved_m) / Decimal(target_m) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if target_m > 0 else 0
        total_saved += saved_m
        total_target += target_m
        goals.append(
            {
                **g,
                "pct": min(pct, 100),
                "saved_formatted": format_money(saved_m, currency, locale),
                "target_formatted": format_money(target_m, currency, locale),
                "remaining_formatted": format_money(remaining_m, currency, locale),
            }
        )

    return {
        "user": user,
        "active_nav": "goals",
        "goals": goals,
        "total_saved_formatted": format_money(total_saved, currency, locale),
        "total_target_formatted": format_money(total_target, currency, locale),
    }


def get_profile_context() -> dict[str, Any]:
    user = get_base_user()
    catalog = load_currency_catalog()
    return {
        "user": user,
        "active_nav": "profile",
        "currencies": get_currency_list(),
        "rates_as_of": catalog.get("as_of", "2026-11-01"),
    }


def get_landing_context() -> dict[str, Any]:
    default_sim = compute_before_you_spend(
        balance_minor=RIYA_PROFILE["current_balance_minor"],
        essentials_minor=RIYA_PROFILE["upcoming_essentials_minor"],
        purchase_minor=49900,
        days_until_income=RIYA_PROFILE["days_until_income"],
        tight_threshold_minor=RIYA_PROFILE["tight_threshold_minor"],
        currency="INR",
        locale="en_IN",
    )
    return {
        "user": get_base_user(),
        "active_nav": "landing",
        "sim": default_sim,
        "currencies": get_currency_list()[:8],  # Top currencies for compact landing selector
        "all_currencies": get_currency_list(),
    }
