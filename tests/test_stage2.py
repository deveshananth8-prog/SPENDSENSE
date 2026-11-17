"""Stage 2 integration & security tests: DB, Auth, CSRF, Demo, Isolation, Avatars, Theme."""

from __future__ import annotations

import io
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import db as db_module
from app.config import settings
from app.main import app
from app.models import Budget, Goal, Transaction, User
from app.security import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, limiter
from app.services.user_data import cleanup_expired_demos


@pytest.fixture()
def isolated_env(tmp_path, monkeypatch):
    db_file = tmp_path / "test_spendsense.db"
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

    yield {"SessionLocal": TestingSessionLocal, "avatar_dir": avatar_dir}

    app.dependency_overrides.clear()
    test_engine.dispose()


def _csrf(client: TestClient) -> str:
    if CSRF_COOKIE_NAME not in client.cookies:
        client.get("/")
    return client.cookies[CSRF_COOKIE_NAME]


def _make_png_bytes(width: int = 400, height: int = 300, color=(194, 103, 74)) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), color)
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_protected_pages_redirect_unauthenticated_to_signin(isolated_env):
    client = TestClient(app)
    for path in [
        "/home",
        "/before-you-spend",
        "/money-buddy",
        "/expenses",
        "/budgets",
        "/goals",
        "/profile",
    ]:
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"].startswith("/signin?next=")


def test_register_login_wrong_password_and_logout(isolated_env):
    client = TestClient(app)
    token = _csrf(client)

    # Reject short password
    bad = client.post(
        "/signup",
        data={
            "name": "Aarav",
            "email": "aarav@example.com",
            "currency": "INR",
            "password": "short",
            "confirm_password": "short",
            "csrf_token": token,
        },
    )
    assert bad.status_code == 400
    assert "at least 8 characters" in bad.text

    # Reject password mismatch
    mismatch = client.post(
        "/signup",
        data={
            "name": "Aarav",
            "email": "aarav@example.com",
            "currency": "INR",
            "password": "password123",
            "confirm_password": "different123",
            "csrf_token": token,
        },
    )
    assert mismatch.status_code == 400
    assert "do not match" in mismatch.text

    # Successful signup
    ok = client.post(
        "/signup",
        data={
            "name": "Aarav Mehta",
            "email": "aarav@example.com",
            "currency": "USD",
            "password": "password123",
            "confirm_password": "password123",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert ok.status_code == 303
    assert ok.headers["location"] == "/home"
    assert SESSION_COOKIE_NAME in client.cookies

    # Verify password stored hashed with argon2
    with isolated_env["SessionLocal"]() as db:
        u = db.query(User).filter(User.email == "aarav@example.com").first()
        assert u is not None
        assert u.password_hash.startswith("$argon2")
        assert u.password_hash != "password123"
        assert u.currency_code == "USD"

    # Profile shows read-only currency and email
    prof = client.get("/profile")
    assert prof.status_code == 200
    assert "USD ($)" in prof.text
    assert "aarav@example.com" in prof.text

    # Log out clears session
    out = client.post("/logout", data={"csrf_token": token}, follow_redirects=False)
    assert out.status_code == 303
    assert client.get("/home", follow_redirects=False).status_code == 303

    # Wrong password returns generic error
    wrong = client.post(
        "/signin",
        data={
            "email": "aarav@example.com",
            "password": "wrongpassword",
            "csrf_token": token,
        },
    )
    assert wrong.status_code == 400
    assert "Invalid email or password." in wrong.text

    # Correct login redirects back to protected target
    login = client.post(
        "/signin",
        data={
            "email": "aarav@example.com",
            "password": "password123",
            "next": "/budgets",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert login.status_code == 303
    assert login.headers["location"] == "/budgets"


def test_csrf_required_on_state_changing_requests(isolated_env):
    client = TestClient(app)
    client.get("/")
    resp = client.post("/demo", data={"csrf_token": "tampered-token"})
    assert resp.status_code == 403


def test_demo_account_seeding_and_expiry_cleanup(isolated_env):
    client = TestClient(app)
    token = _csrf(client)
    resp = client.post("/demo", data={"csrf_token": token}, follow_redirects=True)
    assert resp.status_code == 200
    assert "Demo account" in resp.text
    assert "Hostel Mess &amp; Canteen" in resp.text

    with isolated_env["SessionLocal"]() as db:
        demo_user = db.query(User).filter(User.is_demo.is_(True)).first()
        assert demo_user is not None
        # Age the demo account past TTL and verify cleanup removes it
        demo_user.created_at = datetime.now(timezone.utc) - timedelta(hours=5)
        db.commit()
        cleaned = cleanup_expired_demos(db, upload_dir=isolated_env["avatar_dir"])
        assert cleaned == 1
        assert db.query(User).filter(User.id == demo_user.id).first() is None


def test_data_isolation_between_two_users(isolated_env):
    client_a = TestClient(app)
    client_b = TestClient(app)

    tok_a = _csrf(client_a)
    tok_b = _csrf(client_b)

    client_a.post(
        "/signup",
        data={
            "name": "User Alpha",
            "email": "alpha@example.com",
            "currency": "INR",
            "password": "password123",
            "confirm_password": "password123",
            "csrf_token": tok_a,
        },
    )
    client_b.post(
        "/signup",
        data={
            "name": "User Beta",
            "email": "beta@example.com",
            "currency": "INR",
            "password": "password123",
            "confirm_password": "password123",
            "csrf_token": tok_b,
        },
    )

    # Seed private records strictly for User Alpha
    with isolated_env["SessionLocal"]() as db:
        alpha = db.query(User).filter(User.email == "alpha@example.com").first()
        db.add(
            Transaction(
                user_id=alpha.id,
                amount_minor=45000,
                currency_code="INR",
                category="Food & Mess",
                date=date(2026, 11, 17),
                description="Secret Alpha Supper",
                merchant="Alpha Private Cafe",
                type="expense",
            )
        )
        db.add(Budget(user_id=alpha.id, category="Food & Mess", limit_minor=150000))
        db.add(Goal(user_id=alpha.id, title="Alpha Secret Laptop", target_minor=500000, saved_minor=100000))
        db.commit()

    # Alpha sees her data; Beta does not
    assert "Alpha Private Cafe" in client_a.get("/expenses").text
    assert "Alpha Secret Laptop" in client_a.get("/goals").text

    beta_expenses = client_b.get("/expenses").text
    beta_goals = client_b.get("/goals").text
    beta_home = client_b.get("/home").text
    assert "Alpha Private Cafe" not in beta_expenses
    assert "Alpha Private Cafe" not in beta_home
    assert "Alpha Secret Laptop" not in beta_goals

    # Alpha uploads an avatar; Beta cannot access Alpha's avatar URL
    up = client_a.post(
        "/profile/avatar",
        data={"csrf_token": tok_a},
        files={"avatar": ("photo.png", _make_png_bytes(), "image/png")},
    )
    assert up.status_code == 200
    with isolated_env["SessionLocal"]() as db:
        alpha = db.query(User).filter(User.email == "alpha@example.com").first()
        avatar_name = alpha.avatar_filename
        assert avatar_name is not None

    assert client_a.get(f"/avatars/{avatar_name}").status_code == 200
    assert client_b.get(f"/avatars/{avatar_name}").status_code == 404


def test_avatar_validation_and_remove(isolated_env):
    client = TestClient(app)
    token = _csrf(client)
    client.post(
        "/signup",
        data={
            "name": "Priya Nair",
            "email": "priya@example.com",
            "currency": "INR",
            "password": "password123",
            "confirm_password": "password123",
            "csrf_token": token,
        },
    )

    # 1. Wrong type (text file disguised as .png)
    fake = client.post(
        "/profile/avatar",
        data={"csrf_token": token},
        files={"avatar": ("evil.png", b"not an image at all", "image/png")},
    )
    assert fake.status_code == 400
    assert "valid JPEG, PNG, or WebP" in fake.text

    # 2. Too large (> 2 MB)
    oversized = b"\x89PNG\r\n\x1a\n" + (b"0" * (2 * 1024 * 1024 + 100))
    too_big = client.post(
        "/profile/avatar",
        data={"csrf_token": token},
        files={"avatar": ("big.png", oversized, "image/png")},
    )
    assert too_big.status_code == 400
    assert "2 MB or smaller" in too_big.text

    # 3. Valid PNG resized to 256x256 WebP
    good = client.post(
        "/profile/avatar",
        data={"csrf_token": token},
        files={"avatar": ("pic.png", _make_png_bytes(600, 400), "image/png")},
    )
    assert good.status_code == 200
    assert "Profile picture updated." in good.text
    with isolated_env["SessionLocal"]() as db:
        u = db.query(User).filter(User.email == "priya@example.com").first()
        assert u.avatar_filename is not None
        saved_path = isolated_env["avatar_dir"] / u.avatar_filename
        assert saved_path.is_file()
        with Image.open(saved_path) as out_img:
            assert out_img.size == (256, 256)

    # 4. Remove avatar restores initials fallback
    rem = client.post("/profile/avatar/remove", data={"csrf_token": token}, follow_redirects=True)
    assert rem.status_code == 200
    with isolated_env["SessionLocal"]() as db:
        u = db.query(User).filter(User.email == "priya@example.com").first()
        assert u.avatar_filename is None


def test_theme_persists_to_profile_and_delete_account(isolated_env):
    client = TestClient(app)
    token = _csrf(client)
    client.post(
        "/signup",
        data={
            "name": "Kabir Sen",
            "email": "kabir@example.com",
            "currency": "INR",
            "password": "password123",
            "confirm_password": "password123",
            "csrf_token": token,
        },
    )

    # Save dark theme
    res = client.post(
        "/profile/theme",
        data={"theme": "dark", "csrf_token": token},
        headers={"Accept": "application/json"},
    )
    assert res.status_code == 200
    assert res.json()["theme"] == "dark"

    # Subsequent signed-in page renders server theme
    home = client.get("/home")
    assert 'data-server-theme="dark"' in home.text

    # Change password requires correct current password
    bad_pw = client.post(
        "/profile/password",
        data={
            "current_password": "wrong",
            "new_password": "newpassword123",
            "confirm_new_password": "newpassword123",
            "csrf_token": token,
        },
    )
    assert bad_pw.status_code == 400
    assert "Current password is incorrect." in bad_pw.text

    ok_pw = client.post(
        "/profile/password",
        data={
            "current_password": "password123",
            "new_password": "newpassword123",
            "confirm_new_password": "newpassword123",
            "csrf_token": token,
        },
    )
    assert ok_pw.status_code == 200
    assert "Password updated successfully." in ok_pw.text

    # Delete account removes user and redirects home
    deleted = client.post(
        "/profile/delete",
        data={"confirm_delete": "yes", "csrf_token": token},
        follow_redirects=False,
    )
    assert deleted.status_code == 303
    assert deleted.headers["location"] == "/"
    with isolated_env["SessionLocal"]() as db:
        assert db.query(User).filter(User.email == "kabir@example.com").first() is None


def test_https_proxy_cookies_allow_iframe_sessions_and_csrf(isolated_env):
    # Plain HTTP keeps SameSite=Lax without Secure
    http_client = TestClient(app)
    http_res = http_client.get("/")
    http_cookie = http_res.headers.get("set-cookie", "").lower()
    assert "samesite=lax" in http_cookie
    assert "secure" not in http_cookie

    # Behind container nginx (X-Forwarded-Proto rewritten to http, X-Forwarded-Host is *.run.app)
    nginx_client = TestClient(app)
    nginx_landing = nginx_client.get(
        "/",
        headers={
            "X-Forwarded-Proto": "http",
            "X-Forwarded-Host": "ais-dev-demo.asia-northeast1.run.app",
        },
    )
    nginx_cookie = nginx_landing.headers.get("set-cookie", "").lower()
    assert "samesite=none" in nginx_cookie
    assert "secure" in nginx_cookie
    assert "partitioned" in nginx_cookie

    # Behind HTTPS proxy header, cookies are issued with SameSite=None; Secure; Partitioned
    proxy_client = TestClient(app)
    proxy_landing = proxy_client.get("/", headers={"X-Forwarded-Proto": "https"})
    proxy_cookie = proxy_landing.headers.get("set-cookie", "").lower()
    assert "samesite=none" in proxy_cookie
    assert "secure" in proxy_cookie
    assert "partitioned" in proxy_cookie

    # Over HTTPS transport (e.g. Cloud Run / AI Studio iframe), Secure cookies are sent and accepted
    https_client = TestClient(app, base_url="https://testserver")
    landing = https_client.get("/")
    csrf_set_cookie = landing.headers.get("set-cookie", "").lower()
    assert "samesite=none" in csrf_set_cookie
    assert "secure" in csrf_set_cookie
    assert "partitioned" in csrf_set_cookie

    token = https_client.cookies[CSRF_COOKIE_NAME]
    demo = https_client.post(
        "/demo",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert demo.status_code == 303
    session_set_cookie = demo.headers.get("set-cookie", "").lower()
    assert "samesite=none" in session_set_cookie
    assert "secure" in session_set_cookie
    assert "partitioned" in session_set_cookie
    assert "httponly" in session_set_cookie

    out = https_client.post(
        "/logout",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert out.status_code == 303
    clear_cookie = out.headers.get("set-cookie", "").lower()
    assert "samesite=none" in clear_cookie
    assert "secure" in clear_cookie
    assert "partitioned" in clear_cookie

