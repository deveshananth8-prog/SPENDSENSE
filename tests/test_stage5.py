"""Stage 5 tests: currency conversion, DB persistence, isolation, security, landing AI section, and deployment checks."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import db as db_module
from app.config import settings
from app.db import _normalize_database_url
from app.main import app
from app.models import Budget, Goal, Transaction, User
from app.security import CSRF_COOKIE_NAME, limiter


@pytest.fixture()
def isolated_env(tmp_path, monkeypatch):
    db_file = tmp_path / "stage5_test.db"
    avatar_dir = tmp_path / "avatars"
    avatar_dir.mkdir(parents=True, exist_ok=True)

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

    monkeypatch.setattr(settings, "upload_dir", str(avatar_dir))
    app.dependency_overrides[db_module.get_db] = override_get_db
    limiter._storage.reset()

    yield {"SessionLocal": TestingSessionLocal}

    app.dependency_overrides.clear()
    test_engine.dispose()


def _csrf(client: TestClient) -> str:
    if CSRF_COOKIE_NAME not in client.cookies:
        client.get("/")
    return client.cookies[CSRF_COOKIE_NAME]


def _signup_or_demo(client: TestClient, demo: bool = True, email: str = "user@example.com") -> str:
    token = _csrf(client)
    if demo:
        client.post("/demo", data={"csrf_token": token})
    else:
        client.post(
            "/signup",
            data={
                "name": "Test Student",
                "email": email,
                "currency": "INR",
                "password": "password123",
                "confirm_password": "password123",
                "csrf_token": token,
            },
        )
    return token


def test_landing_ai_transparency_privacy_and_health(isolated_env):
    client = TestClient(app)
    res = client.get("/")
    assert res.status_code == 200
    assert "How SpendSense uses AI" in res.text
    assert "Numbers are calculated in code" in res.text
    assert "Privacy &amp; what we store" in res.text
    assert "X-Content-Type-Options" in res.headers
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "stage": 5}


def test_profile_currency_preview_and_inr_usd_jpy_conversion(isolated_env):
    client = TestClient(app)
    token = _signup_or_demo(client, demo=True)

    # Preview INR -> USD
    prev_usd = client.post(
        "/profile/currency/preview",
        json={"target_currency": "USD"},
        headers={"X-CSRF-Token": token},
    )
    assert prev_usd.status_code == 200
    data = prev_usd.json()
    assert data["from_currency"] == "INR"
    assert data["to_currency"] == "USD"
    assert any(r["label"] == "Monthly allowance" and "$" in r["after"] for r in data["rows"])

    # Convert INR -> USD
    conv_usd = client.post(
        "/profile/currency/convert",
        data={"target_currency": "USD", "csrf_token": token},
    )
    assert conv_usd.status_code == 200
    assert "Working currency switched to USD" in conv_usd.text

    # Convert USD -> JPY (0 decimals) and verify allowance & formatting across pages
    conv_jpy = client.post(
        "/profile/currency/convert",
        data={"target_currency": "JPY", "csrf_token": token},
    )
    assert conv_jpy.status_code == 200
    assert "Working currency switched to JPY" in conv_jpy.text

    with isolated_env["SessionLocal"]() as db:
        u = db.query(User).filter(User.is_demo.is_(True)).first()
        assert u.currency_code == "JPY"
        assert u.monthly_allowance_minor > 0

    home = client.get("/home")
    assert home.status_code == 200
    assert "¥" in home.text or "JPY" in home.text


def test_expenses_budgets_goals_persistence_and_user_isolation(isolated_env):
    client_a = TestClient(app)
    client_b = TestClient(app)
    tok_a = _signup_or_demo(client_a, demo=False, email="alice@example.com")
    tok_b = _signup_or_demo(client_b, demo=False, email="bob@example.com")

    # Alice saves a quick expense
    created = client_a.post(
        "/api/expenses/quick-save",
        json={
            "merchant": "Campus Canteen",
            "amount": "120",
            "currency": "INR",
            "category": "Food & Mess",
            "date": date.today().isoformat(),
            "type": "expense",
            "confirm_currency_mismatch": False,
        },
        headers={"X-CSRF-Token": tok_a},
    )
    assert created.status_code == 201
    tx_id = created.json()["id"]

    # Bob cannot update or delete Alice's expense
    bob_upd = client_b.post(
        f"/api/expenses/{tx_id}/update",
        json={
            "merchant": "Hacked",
            "amount": "999",
            "category": "Other",
            "date": date.today().isoformat(),
            "note": "",
        },
        headers={"X-CSRF-Token": tok_b},
    )
    assert bob_upd.status_code == 404

    bob_del = client_b.post(
        f"/api/expenses/{tx_id}/delete",
        json={},
        headers={"X-CSRF-Token": tok_b},
    )
    assert bob_del.status_code == 404

    # Alice updates her expense
    upd = client_a.post(
        f"/api/expenses/{tx_id}/update",
        json={
            "merchant": "Campus Mess Hall",
            "amount": "150",
            "category": "Food & Mess",
            "date": date.today().isoformat(),
            "note": "Updated lunch",
        },
        headers={"X-CSRF-Token": tok_a},
    )
    assert upd.status_code == 200
    assert upd.json()["amount_minor"] == 15000
    assert "Campus Mess Hall" in client_a.get("/expenses").text

    # Alice creates a budget and a goal, and both persist in pages
    b_res = client_a.post(
        "/api/budgets/update",
        json={"category": "Food & Mess", "limit": "2500"},
        headers={"X-CSRF-Token": tok_a},
    )
    assert b_res.status_code == 200
    assert "2,500" in client_a.get("/budgets").text

    g_res = client_a.post(
        "/api/goals/create",
        json={
            "title": "Lab Calculator",
            "target": "1500",
            "saved": "300",
            "deadline": "2027-01-15",
            "note": "Engineering",
        },
        headers={"X-CSRF-Token": tok_a},
    )
    assert g_res.status_code == 201
    assert "Lab Calculator" in client_a.get("/goals").text

    # Alice deletes her expense
    d_res = client_a.post(
        f"/api/expenses/{tx_id}/delete",
        json={},
        headers={"X-CSRF-Token": tok_a},
    )
    assert d_res.status_code == 200
    assert "Campus Mess Hall" not in client_a.get("/expenses").text


def test_no_stage1_preview_copy_and_deployment_hygiene(isolated_env):
    client = TestClient(app)
    _signup_or_demo(client, demo=True)
    for path in ["/expenses", "/budgets", "/goals", "/before-you-spend", "/profile"]:
        page = client.get(path)
        assert page.status_code == 200
        assert "Stage 1 UI preview" not in page.text
        assert "Preview loading" not in page.text
        assert "Preview error" not in page.text

    # Database URL normalization supports Render/Railway postgres:// URIs
    assert _normalize_database_url("postgres://user:pass@host/db") == "postgresql+psycopg://user:pass@host/db"
    assert _normalize_database_url("postgresql://user:pass@host/db") == "postgresql+psycopg://user:pass@host/db"
    assert _normalize_database_url("sqlite:///./spendsense.db") == "sqlite:///./spendsense.db"

    # .gitignore covers secrets, DBs, and uploads
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    for pattern in [".env", "*.db", "uploads/"]:
        assert pattern in gitignore
