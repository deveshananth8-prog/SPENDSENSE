"""Stage 4 tests: Parsers, Grounded Snapshot Isolation, Offline Mode, and Mocked Gemini Endpoints."""

from __future__ import annotations

import io
import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import db as db_module
from app.config import settings
from app.main import app
from app.models import Budget, Goal, MerchantCategory, Transaction, User
from app.security import CSRF_COOKIE_NAME, hash_password, limiter
from app.services import ai_client
from app.services.parsers import parse_transaction_text
from app.services.snapshot import build_financial_snapshot


@pytest.fixture()
def stage4_env(tmp_path, monkeypatch):
    db_file = tmp_path / "test_stage4.db"
    test_engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    TestingSessionLocal = sessionmaker(
        bind=test_engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
    db_module.Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(settings, "gemini_api_key", "")
    ai_client._clear_ai_cache()
    app.dependency_overrides[db_module.get_db] = override_get_db
    limiter._storage.reset()

    yield {"SessionLocal": TestingSessionLocal}

    ai_client._clear_ai_cache()
    app.dependency_overrides.clear()
    test_engine.dispose()


def _csrf(client: TestClient) -> str:
    if CSRF_COOKIE_NAME not in client.cookies:
        client.get("/")
    return client.cookies[CSRF_COOKIE_NAME]


def _signup(client: TestClient, email: str, name: str = "Riya Test", currency: str = "INR") -> str:
    token = _csrf(client)
    resp = client.post(
        "/signup",
        data={
            "name": name,
            "email": email,
            "currency": currency,
            "password": "password123",
            "confirm_password": "password123",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    return token


def _make_png_bytes(width: int = 120, height: int = 120) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), (210, 110, 80))
    img.save(buf, format="PNG")
    return buf.getvalue()


class _FakeGeminiClient:
    """Deterministic fake google.genai.Client (never hits network)."""

    def __init__(self, handler):
        self.calls = []
        self._handler = handler
        self.models = SimpleNamespace(generate_content=self._generate_content)

    def _generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        payload = self._handler(model=model, contents=contents, config=config)
        return SimpleNamespace(text=json.dumps(payload))


# ---------------------------------------------------------------------------
# 1. Pure Parser Tests (SMS formats, multi-currency, natural shorthand)
# ---------------------------------------------------------------------------

def test_regex_parser_indian_upi_and_global_currencies():
    ref = date(2026, 11, 17)

    inr_sms = parse_transaction_text(
        "Rs 245.00 debited from a/c **4192 via UPI to Zomato on 17-Nov",
        default_currency="INR",
        today=ref,
    )
    assert inr_sms.amount_minor == 24500
    assert inr_sms.currency == "INR"
    assert "Zomato" in inr_sms.merchant
    assert inr_sms.category == "Food & Mess"
    assert inr_sms.date == "2026-11-17"
    assert inr_sms.type == "expense"

    usd_sms = parse_transaction_text(
        "$14.50 spent at Trader Joe's on 16-Nov",
        default_currency="INR",
        today=ref,
    )
    assert usd_sms.amount_minor == 1450
    assert usd_sms.currency == "USD"
    assert usd_sms.category == "Food & Mess"
    assert usd_sms.date == "2026-11-16"

    eur_sms = parse_transaction_text(
        "€22.40 paid at Carrefour on 15-Nov",
        default_currency="INR",
        today=ref,
    )
    assert eur_sms.amount_minor == 2240
    assert eur_sms.currency == "EUR"

    gbp_sms = parse_transaction_text(
        "GBP 18.00 debited to Uber on 14-Nov",
        default_currency="INR",
        today=ref,
    )
    assert gbp_sms.amount_minor == 1800
    assert gbp_sms.currency == "GBP"
    assert gbp_sms.category == "Travel"

    credited = parse_transaction_text(
        "INR 5000 credited to a/c for monthly allowance",
        default_currency="INR",
        today=ref,
    )
    assert credited.amount_minor == 500000
    assert credited.type == "income"


def test_regex_parser_natural_text_and_rejects_no_amount():
    ref = date(2026, 11, 17)

    chai = parse_transaction_text("chai 20", default_currency="INR", today=ref)
    assert chai.amount_minor == 2000
    assert chai.currency == "INR"
    assert chai.category == "Food & Mess"
    assert chai.date == "2026-11-17"

    auto = parse_transaction_text("auto 80 yesterday", default_currency="INR", today=ref)
    assert auto.amount_minor == 8000
    assert auto.category == "Travel"
    assert auto.date == (ref - timedelta(days=1)).isoformat()

    for bad in ["bought snacks", "hello there", "Rs 0 chai"]:
        with pytest.raises(ValueError):
            parse_transaction_text(bad, default_currency="INR", today=ref)


# ---------------------------------------------------------------------------
# 2. Grounded Financial Snapshot & Two-User Isolation
# ---------------------------------------------------------------------------

def test_snapshot_builder_user_isolation_and_last_10(stage4_env):
    with stage4_env["SessionLocal"]() as db:
        alpha = User(
            name="Alpha Student",
            email="alpha-snap@example.com",
            password_hash=hash_password("password123"),
            currency_code="INR",
            monthly_allowance_minor=500000,
            next_income_date=date(2026, 11, 29),
            tight_threshold_minor=10000,
        )
        beta = User(
            name="Beta Student",
            email="beta-snap@example.com",
            password_hash=hash_password("password123"),
            currency_code="USD",
            monthly_allowance_minor=120000,
            next_income_date=date(2026, 11, 29),
            tight_threshold_minor=1500,
        )
        db.add_all([alpha, beta])
        db.flush()

        for i in range(12):
            db.add(
                Transaction(
                    user_id=alpha.id,
                    amount_minor=10000,
                    currency_code="INR",
                    category="Food & Mess",
                    date=date(2026, 11, 1 + i),
                    description=f"Meal {i}",
                    merchant=f"Alpha Mess {i}",
                    type="expense",
                )
            )
        db.add(Budget(user_id=alpha.id, category="Food & Mess", limit_minor=150000))
        db.add(Goal(user_id=alpha.id, title="Alpha Kindle", target_minor=800000, saved_minor=200000))

        db.add(
            Transaction(
                user_id=beta.id,
                amount_minor=9900,
                currency_code="USD",
                category="Shopping",
                date=date(2026, 11, 15),
                description="Secret Beta Order",
                merchant="Beta Secret Store",
                type="expense",
            )
        )
        db.add(Goal(user_id=beta.id, title="Beta Secret Bike", target_minor=50000, saved_minor=10000))
        db.commit()

        snap_a = build_financial_snapshot(db, alpha, today=date(2026, 11, 17))
        snap_b = build_financial_snapshot(db, beta, today=date(2026, 11, 17))

        assert snap_a["user_currency"] == "INR"
        assert snap_a["monthly_expenses_minor"] == 120000
        assert len(snap_a["last_10_transactions"]) == 10
        assert snap_a["budgets_used"][0]["pct"] == 80
        assert snap_a["goals_progress"][0]["title"] == "Alpha Kindle"
        snap_a_json = json.dumps(snap_a)
        assert "Beta Secret Store" not in snap_a_json
        assert "Beta Secret Bike" not in snap_a_json

        assert snap_b["user_currency"] == "USD"
        assert snap_b["monthly_expenses_minor"] == 9900
        assert "Alpha Mess" not in json.dumps(snap_b)


# ---------------------------------------------------------------------------
# 3. Offline Mode Automatic Fallback Tests (No API Key)
# ---------------------------------------------------------------------------

def test_offline_mode_fallbacks_when_key_missing(stage4_env):
    client = TestClient(app)
    token = _signup(client, "offline@example.com", currency="INR")

    # Money Buddy uses grounded offline fallback and sets offline_mode=True
    buddy = client.post(
        "/api/ai/money-buddy",
        json={"question": "Where am I spending most of my money?"},
        headers={"X-CSRF-Token": token},
    )
    assert buddy.status_code == 200
    bdata = buddy.json()
    assert bdata["offline_mode"] is True
    assert len(bdata["why"]) >= 2
    assert "₹" in bdata["answer"]

    # Quick Add text works offline via regex parser
    qa = client.post(
        "/api/ai/quick-add/parse",
        json={"text": "auto 80 yesterday"},
        headers={"X-CSRF-Token": token},
    )
    assert qa.status_code == 200
    qdata = qa.json()
    assert qdata["offline_mode"] is True
    assert qdata["amount_minor"] == 8000
    assert qdata["category"] == "Travel"

    # Screenshot vision gives clear 503 offline guidance when no key is set
    shot = client.post(
        "/api/ai/quick-add/screenshot",
        files={"screenshot": ("pay.png", _make_png_bytes(), "image/png")},
        headers={"X-CSRF-Token": token},
    )
    assert shot.status_code == 503
    assert shot.json()["offline_mode"] is True
    assert "Offline mode" in shot.json()["detail"]

    # Home narrative & Before You Spend explanation also work offline
    home_ai = client.post("/api/ai/home-narrative", json={}, headers={"X-CSRF-Token": token})
    assert home_ai.status_code == 200
    assert home_ai.json()["offline_mode"] is True

    bys_ai = client.post(
        "/api/ai/explain-affordability",
        json={
            "item": "Headphones",
            "verdict": "Tight",
            "balance_formatted": "₹2,480.00",
            "essentials_formatted": "₹850.00",
            "purchase_formatted": "₹1,199.00",
            "safe_to_spend_formatted": "₹1,630.00",
            "left_after_buying_formatted": "₹431.00",
            "daily_before_formatted": "₹135.83",
            "daily_after_formatted": "₹35.92",
            "tight_threshold_formatted": "₹100.00",
            "days": 12,
        },
        headers={"X-CSRF-Token": token},
    )
    assert bys_ai.status_code == 200
    assert bys_ai.json()["offline_mode"] is True
    assert "₹431.00" in bys_ai.json()["explanation"]


# ---------------------------------------------------------------------------
# 4. Mocked Gemini Client Integration, Currency Mismatch, Memory & Security
# ---------------------------------------------------------------------------

def test_mocked_gemini_endpoints_currency_mismatch_and_merchant_memory(stage4_env, monkeypatch):
    secret_sentinel = "AIzaTestSuperSecretKey987654321"
    monkeypatch.setattr(settings, "gemini_api_key", secret_sentinel)

    def fake_handler(*, model, contents, config):
        sys_inst = getattr(config, "system_instruction", "") or ""
        if "Money Buddy" in sys_inst:
            return {
                "answer": "You spent ₹245.00 on Food & Mess and still have ₹5,755.00 left this cycle.",
                "next_step": "Check Before You Spend before ordering dinner tonight.",
                "why": ["Monthly expenses: ₹245.00", "Current balance: ₹5,755.00"],
            }
        if "payment/UPI screenshot" in sys_inst:
            return {
                "amount": 14.5,
                "currency": "USD",
                "merchant": "Campus Espresso",
                "category": "Food & Mess",
                "date": "2026-11-17",
                "type": "expense",
            }
        if "Extract a single financial transaction" in sys_inst:
            return {
                "amount": 18.25,
                "currency": "USD",
                "merchant": "Campus Espresso",
                "category": "Food & Mess",
                "date": "2026-11-17",
                "type": "expense",
            }
        if "Pick the best single category" in sys_inst:
            return {"category": "Education"}
        if "student-friendly financial summaries" in sys_inst:
            return {
                "monthly_summary": "Your ₹6,000.00 allowance is pacing well.",
                "insight_bodies": ["Food & Mess is your main spend so far.", "Runway stays Safe."],
            }
        if "Before You Spend verdict" in sys_inst:
            return {
                "explanation": "With ₹1,630.00 safe to spend, ₹1,199.00 leaves ₹431.00 across 12 days."
            }
        return {}

    fake_client = _FakeGeminiClient(fake_handler)
    monkeypatch.setattr(ai_client, "_create_gemini_client", lambda: fake_client)

    client = TestClient(app)
    token = _signup(client, "gemini-mock@example.com", currency="INR")

    # 1. Money Buddy calls mocked Gemini and uses single config model constant
    buddy = client.post(
        "/api/ai/money-buddy",
        json={"question": "How am I doing?"},
        headers={"X-CSRF-Token": token},
    )
    assert buddy.status_code == 200
    assert buddy.json()["offline_mode"] is False
    assert "₹5,755.00" in buddy.json()["answer"]
    assert fake_client.calls[-1]["model"] == settings.gemini_model

    # 2. Quick Add SMS detects foreign currency (USD != INR)
    parsed = client.post(
        "/api/ai/quick-add/parse",
        json={"text": "$18.25 paid at Campus Espresso"},
        headers={"X-CSRF-Token": token},
    )
    assert parsed.status_code == 200
    pdata = parsed.json()
    assert pdata["offline_mode"] is False
    assert pdata["currency"] == "USD"
    assert pdata["currency_mismatch"] is True

    # 3. Saving mismatched currency without confirmation returns 409
    unconfirmed = client.post(
        "/api/expenses/quick-save",
        json={
            "merchant": "Campus Espresso",
            "amount": "18.25",
            "currency": "USD",
            "category": "Education",
            "date": "2026-11-17",
            "type": "expense",
            "confirm_currency_mismatch": False,
        },
        headers={"X-CSRF-Token": token},
    )
    assert unconfirmed.status_code == 409
    assert unconfirmed.json()["requires_currency_confirmation"] is True

    # 4. Saving with confirm_currency_mismatch=True persists Transaction + MerchantCategory
    saved = client.post(
        "/api/expenses/quick-save",
        json={
            "merchant": "Campus Espresso",
            "amount": "18.25",
            "currency": "USD",
            "category": "Education",
            "date": "2026-11-17",
            "type": "expense",
            "confirm_currency_mismatch": True,
        },
        headers={"X-CSRF-Token": token},
    )
    assert saved.status_code == 201
    assert saved.json()["amount_minor"] == 1825
    assert saved.json()["currency"] == "USD"

    with stage4_env["SessionLocal"]() as db:
        mem_row = db.query(MerchantCategory).first()
        assert mem_row is not None
        assert mem_row.category == "Education"

    # 5. Live category suggestion recalls user's corrected category from memory
    sugg = client.post(
        "/api/ai/suggest-category",
        json={"description": "Campus Espresso"},
        headers={"X-CSRF-Token": token},
    )
    assert sugg.status_code == 200
    assert sugg.json()["category"] == "Education"
    assert sugg.json()["source"] == "memory"

    # 6. Payment screenshot vision uses mocked Gemini and recalls remembered category
    shot = client.post(
        "/api/ai/quick-add/screenshot",
        files={"screenshot": ("receipt.png", _make_png_bytes(), "image/png")},
        headers={"X-CSRF-Token": token},
    )
    assert shot.status_code == 200
    sdata = shot.json()
    assert sdata["offline_mode"] is False
    assert sdata["amount_minor"] == 1450
    assert sdata["category"] == "Education"

    # 7. Reject oversized (>4 MB) and invalid screenshots
    big_shot = client.post(
        "/api/ai/quick-add/screenshot",
        files={"screenshot": ("huge.png", b"\x89PNG\r\n\x1a\n" + b"0" * (4 * 1024 * 1024 + 50), "image/png")},
        headers={"X-CSRF-Token": token},
    )
    assert big_shot.status_code == 400

    bad_shot = client.post(
        "/api/ai/quick-add/screenshot",
        files={"screenshot": ("fake.png", b"not-an-image", "image/png")},
        headers={"X-CSRF-Token": token},
    )
    assert bad_shot.status_code == 400

    # 8. Home narrative & Before You Spend explain endpoints
    home_res = client.post("/api/ai/home-narrative", json={}, headers={"X-CSRF-Token": token})
    assert home_res.status_code == 200
    assert home_res.json()["offline_mode"] is False

    bys_res = client.post(
        "/api/ai/explain-affordability",
        json={
            "item": "Speaker",
            "verdict": "Tight",
            "balance_formatted": "₹2,480.00",
            "essentials_formatted": "₹850.00",
            "purchase_formatted": "₹1,199.00",
            "safe_to_spend_formatted": "₹1,630.00",
            "left_after_buying_formatted": "₹431.00",
            "daily_before_formatted": "₹135.83",
            "daily_after_formatted": "₹35.92",
            "tight_threshold_formatted": "₹100.00",
            "days": 12,
        },
        headers={"X-CSRF-Token": token},
    )
    assert bys_res.status_code == 200
    assert bys_res.json()["offline_mode"] is False

    # 9. Verify secret API key NEVER appears in any HTML page or JSON response
    for page in ["/home", "/money-buddy", "/expenses", "/before-you-spend"]:
        html = client.get(page).text
        assert secret_sentinel not in html
    assert secret_sentinel not in buddy.text
    assert secret_sentinel not in home_res.text

    # 10. Unauthenticated & bad CSRF security checks
    anon = TestClient(app)
    assert anon.post("/api/ai/money-buddy", json={"question": "hi"}).status_code == 401
    bad_csrf = client.post(
        "/api/ai/money-buddy",
        json={"question": "hi"},
        headers={"X-CSRF-Token": "wrong-token"},
    )
    assert bad_csrf.status_code == 403


def test_gemini_server_error_retries_and_falls_back_cleanly(stage4_env, monkeypatch):
    from google.genai import errors as genai_errors

    monkeypatch.setattr(settings, "gemini_api_key", "AIzaFakeKeyForRetryTest")
    monkeypatch.setattr(ai_client.time, "sleep", lambda _sec: None)

    attempts = {"count": 0}

    def flaky_handler(*, model, contents, config):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise genai_errors.ServerError(503, {"error": {"message": "Service unavailable", "status": "UNAVAILABLE"}})
        return {
            "answer": "Recovered on retry using ₹6,000.00 allowance.",
            "next_step": "Keep tracking daily expenses.",
            "why": ["Monthly allowance: ₹6,000.00"],
        }

    fake_client = _FakeGeminiClient(flaky_handler)
    monkeypatch.setattr(ai_client, "_create_gemini_client", lambda: fake_client)

    client = TestClient(app)
    token = _signup(client, "retry-ok@example.com", currency="INR")

    # 1st call fails with 503 ServerError, 2nd attempt succeeds
    res = client.post(
        "/api/ai/money-buddy",
        json={"question": "How is my budget?"},
        headers={"X-CSRF-Token": token},
    )
    assert res.status_code == 200
    assert res.json()["offline_mode"] is False
    assert attempts["count"] == 2

    # Persistent ServerError on both attempts falls back gracefully to offline mode
    def always_503(*, model, contents, config):
        raise genai_errors.ServerError(503, {"error": {"message": "High demand", "status": "UNAVAILABLE"}})

    monkeypatch.setattr(ai_client, "_create_gemini_client", lambda: _FakeGeminiClient(always_503))
    ai_client._clear_ai_cache()
    res_offline = client.post(
        "/api/ai/money-buddy",
        json={"question": "Summarise my spending."},
        headers={"X-CSRF-Token": token},
    )
    assert res_offline.status_code == 200
    assert res_offline.json()["offline_mode"] is True

    # 429 ClientError skips redundant retry and returns friendly 429 on screenshot
    calls_429 = {"count": 0}

    def always_429(*, model, contents, config):
        calls_429["count"] += 1
        raise genai_errors.ClientError(429, {"error": {"message": "Quota exceeded", "status": "RESOURCE_EXHAUSTED"}})

    monkeypatch.setattr(ai_client, "_create_gemini_client", lambda: _FakeGeminiClient(always_429))
    shot_429 = client.post(
        "/api/ai/quick-add/screenshot",
        files={"screenshot": ("pay.png", _make_png_bytes(), "image/png")},
        headers={"X-CSRF-Token": token},
    )
    assert shot_429.status_code == 429
    assert calls_429["count"] == 1
    assert shot_429.json()["offline_mode"] is True

