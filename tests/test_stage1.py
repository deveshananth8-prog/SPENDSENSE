"""Stage 1 unit and route smoke tests for SpendSense AI."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.money import format_money, get_currency_list
from app.services.stage1_data import compute_before_you_spend, compute_runway
from data.sample_data import RIYA_EXPENSES

client = TestClient(app)


def test_format_money_indian_grouping_and_precisions():
    assert format_money(12500000, "INR", "en_IN") == "₹1,25,000.00"
    assert format_money(600000, "INR", "en_IN") == "₹6,000.00"
    assert format_money(12500000, "USD", "en_US") == "$125,000.00"
    assert format_money(125000, "JPY", "ja_JP") == "￥125,000"
    assert format_money(125500, "KWD", "en_US") == "KWD125.500"
    assert format_money(125000, "EUR", "en_IE") == "€1,250.00"


def test_currency_catalog_contains_major_currencies():
    codes = {c["code"] for c in get_currency_list()}
    for required in ["INR", "USD", "EUR", "GBP", "JPY", "KWD", "SGD", "AED", "KRW"]:
        assert required in codes
    assert len(codes) >= 31


def test_before_you_spend_verdicts_and_edge_cases():
    # Comfortable
    res_ok = compute_before_you_spend(
        balance_minor=248000,
        essentials_minor=85000,
        purchase_minor=20000,
        days_until_income=12,
        tight_threshold_minor=10000,
    )
    assert res_ok["verdict"] == "Comfortable"
    assert res_ok["safe_to_spend_minor"] == 163000
    assert res_ok["left_after_buying_minor"] == 143000

    # Tight (daily_after < 10000)
    res_tight = compute_before_you_spend(
        balance_minor=248000,
        essentials_minor=85000,
        purchase_minor=119900,
        days_until_income=12,
        tight_threshold_minor=10000,
    )
    assert res_tight["verdict"] == "Tight"
    assert res_tight["left_after_buying_minor"] == 43100

    # Not now (essentials > balance or left_after < 0)
    res_no = compute_before_you_spend(
        balance_minor=50000,
        essentials_minor=85000,
        purchase_minor=0,
        days_until_income=0,
        tight_threshold_minor=10000,
    )
    assert res_no["verdict"] == "Not now"
    assert res_no["days"] == 1
    assert res_no["left_after_buying_minor"] == -35000


def test_runway_calculation_riya_safe():
    runway = compute_runway(
        balance_minor=248000,
        essentials_minor=85000,
        days_until_income=12,
        expenses=RIYA_EXPENSES,
    )
    assert runway["status"] == "Safe"
    assert runway["runway_days"] >= 12


def test_all_stage1_routes_render_cleanly():
    routes = [
        ("/", "Know if you can afford it before you pay."),
        ("/signin", "Sign in to SpendSense"),
        ("/signup", "Create your account"),
        ("/home", "Money Runway"),
        ("/before-you-spend", "How we calculated this"),
        ("/money-buddy", "Why this answer?"),
        ("/expenses", "Quick Add"),
        ("/budgets", "Monthly Budgets"),
        ("/goals", "Your Goals"),
        ("/profile", "Profile picture"),
    ]
    for path, expected_text in routes:
        resp = client.get(path)
        assert resp.status_code == 200, f"Failed on {path}"
        assert expected_text in resp.text
        assert "SpendSense gives general guidance, not professional financial advice." in resp.text
