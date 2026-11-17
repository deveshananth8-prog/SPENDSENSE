# SpendSense AI

**Know before you spend.** An AI money companion for students and young adults worldwide, with India as the first and best-supported market (UPI-style SMS parsing and hostel-student sample data).

Other apps tell you where your money went; SpendSense tells you whether you can afford something **before** you spend, and warns you **before** you run out of money.

---

## Key Features

- **Money Runway Bar (Hero):** Maps your safe-to-spend balance (after subtracting upcoming essentials) and 14-day daily spending pace onto a timeline from today to your next allowance date.
- **Before You Spend Simulator:** Deterministic minor-unit affordability check (`Comfortable`, `Tight`, or `Not now`) with live Money Runway impact markers, exact calculation breakdown, three actionable alternatives (wait N days, cheaper price cap, split in two), "Save as a goal instead", and plain-language AI commentary.
- **Money Buddy (Notebook UI):** Ask plain questions in English or Hinglish about your month. Every response only cites your grounded snapshot numbers and includes a collapsible **"Why this answer?"** breakdown.
- **Quick Add (SMS / Natural Text / Screenshot):** Paste bank/UPI SMS messages, type shorthand like `chai 20` or `auto 80 yesterday`, or scan a payment screenshot (Gemini Vision) into an editable confirmation card, with currency mismatch warnings and per-user merchant category memory.
- **Multi-Currency Support & Profile Conversion:** Format and convert amounts accurately across world currencies (`INR`, `USD`, `EUR`, `GBP`, `JPY`, `KWD`, etc.) using Babel decimal precision, with an itemized conversion preview before switching.
- **Budgets, Goals & Light/Dark Editorial Theme:** Monthly category caps, savings goals, responsive phone/tablet/desktop layouts, and zero-flash Light/Dark/System themes persisted to your account.

---

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, Jinja2, SQLAlchemy 2.0 (SQLite or PostgreSQL via `psycopg`), Pydantic Settings
- **Security:** Argon2id password hashing (`argon2-cffi`), HMAC-signed HttpOnly session cookies, double-submit CSRF protection, SlowAPI per-IP/per-user rate limiting, Pillow EXIF-stripped 256×256 WebP avatar sanitization
- **AI:** `google-genai` Python SDK (`gemini-3.1-flash-lite`) strictly behind `/api/ai/*` server routes, with structured JSON schemas and deterministic offline fallbacks
- **Money & Formatting:** Python `Decimal`, integer minor units, Babel (`babel.numbers`)
- **Frontend:** Semantic HTML, CSS custom properties (zero external CSS build step), vanilla JS, Chart.js, Lucide icons

---

## Architecture

```text
app/
  main.py            # FastAPI entrypoint, security headers, CSRF & rate-limit middleware
  config.py          # Environment-backed pydantic-settings & GEMINI_MODEL constant
  db.py              # SQLAlchemy engine (SQLite + PostgreSQL URL normalization)
  models.py          # User, Transaction, Budget, Goal, MerchantCategory ORM models
  security.py        # Argon2id hashing, HMAC session cookies, CSRF verification, rate keys
  routers/
    pages.py         # SSR routes (Landing, Home, Before You Spend, Money Buddy, Expenses, Budgets, Goals)
    auth.py          # Sign up, Sign in, Log out, Try the demo (auto-expiring sample account)
    profile.py       # Profile info, currency preview & atomic conversion, theme, password, avatars, delete
    ai.py            # Server-only Gemini endpoints + Expense/Budget/Goal persistence endpoints
  services/
    stage1_data.py   # Pure affordability & Money Runway math (Decimal + minor units)
    money.py         # Minor-unit Decimal conversion & Babel locale formatting
    snapshot.py      # Strictly user-scoped financial snapshot builder for AI grounding
    parsers.py       # Offline/regex SMS & natural-text parser + keyword fallback categorization
    ai_client.py     # Server-side Gemini SDK client (10s timeout, retry, backoff, offline fallback)
    avatars.py       # Pillow JPEG/PNG/WebP validation, EXIF strip, 256x256 WebP export
    user_data.py     # User-isolated queries, view-model builders, demo seeding/cleanup
  templates/         # Jinja2 base layout, macros, pages, and SVG illustrations
  static/            # CSS tokens/styles, vanilla JS calculators & interactions, Chart.js & Lucide
data/
  rates.json         # Static reference currency rates (relative to INR) & Babel metadata
  sample_data.py     # Riya's ₹6,000 hostel student demo dataset
tests/               # Pytest suites covering calculation math, auth/security, AI grounding, and Stage 5 polish
```

---

## Local Setup

1. **Create and activate a virtual environment**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. **Install dependencies**

```bash
pip install -r requirements.txt
```

3. **Configure environment variables**

```bash
cp .env.example .env
# Edit .env and set a strong SECRET_KEY and your GEMINI_API_KEY
```

4. **Run the development server (port 3000)**

```bash
uvicorn app.main:app --reload --port 3000
```

Open `http://localhost:3000`.

5. **Run the test suite**

```bash
pytest -v
```

---

## Environment Variables

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `SECRET_KEY` | Yes (prod) | `dev-stage2-change-me-in-production` | Signs session & CSRF cookies; must be a long random secret in production. |
| `GEMINI_API_KEY` | Optional | `""` | Server-side Gemini API key. If omitted or unavailable, SpendSense switches cleanly to grounded offline fallbacks. |
| `DATABASE_URL` | No | `sqlite:///./spendsense.db` | SQLite path or PostgreSQL URI (`postgres://...` / `postgresql://...`). |
| `UPLOAD_DIR` | No | `uploads/avatars` | Directory where sanitized 256×256 WebP avatars are saved. |
| `ENVIRONMENT` | No | `development` | Set to `production` to enforce HTTPS-only `Secure` cookies and startup secret checks. |

---

## How AI Is Grounded

1. **Code calculates everything:** Affordability verdicts, safe-to-spend balances, runway projections, budget usage, and currency conversions are computed deterministically in Python (`app/services/stage1_data.py`, `app/services/money.py`, `app/services/snapshot.py`).
2. **Snapshot-only context:** When Money Buddy or Home Narrative calls Gemini, only the user's pre-computed `FinancialSnapshot` (currency, category totals, income/expenses, runway summary, budgets, goals, insights, last 10 transactions) is sent—the model is instructed to treat user prompts as untrusted text and never invent figures.
3. **Inspectable working & graceful offline mode:** Every Money Buddy note provides a collapsible **"Why this answer?"** panel, Before You Spend displays **"How we calculated this"**, and every Gemini call has a 10-second timeout, bounded retry, and grounded offline fallback.

---

## Currency System & Limitations

- All money values are stored as **integers in minor units** (`paise`, `cents`, `yen`, `fils`) using Babel's `get_currency_precision()` (0 decimals for `JPY`/`KRW`/`VND`, 3 decimals for `KWD`/`BHD`/`OMR`, 2 decimals for most currencies) and Python `Decimal` (`ROUND_HALF_UP`).
- `data/rates.json` provides **approximate static reference rates** (with an explicit `as_of` date shown in the UI). They are designed for student budgeting convenience when switching working currency—not live FX trading quotes.

---

## Security Notes

- **Passwords:** Hashed with Argon2id (`argon2-cffi`); minimum 8 characters enforced.
- **Sessions & Cookies:** Signed with HMAC-SHA256 (`SECRET_KEY`), `HttpOnly`, and `Secure` enforced in `ENVIRONMENT=production` (and behind HTTPS reverse proxies).
- **CSRF & Rate Limiting:** Double-submit HMAC-signed CSRF token verified on all state-changing forms and JSON/multipart `/api/*` endpoints; SlowAPI limits sign-in, sign-up, password updates, demo creation, and per-user AI endpoints.
- **User Isolation & Uploads:** Every DB read/write filters by the authenticated `user.id`. Avatars are capped at 2 MB, verified via Pillow, re-encoded from pixel buffers as 256×256 WebP (stripping EXIF metadata), stored under random filenames, and served only to the owning user.

---

## Deployment (Render / Railway)

A `Procfile` and `render.yaml` are included.

- **Start command:**

```bash
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-3000} --proxy-headers --forwarded-allow-ips='*'
```

- **Important Persistence Warning:** On PaaS hosts with ephemeral filesystems (default Railway containers or free Render instances without a mounted disk), local **SQLite (`spendsense.db`) and uploaded avatars (`uploads/avatars/`) are wiped on every redeploy or restart**. Attach a **persistent disk** (e.g. `/var/data` as configured in `render.yaml` with `DATABASE_URL=sqlite:////var/data/spendsense.db` and `UPLOAD_DIR=/var/data/uploads/avatars`) or provision **PostgreSQL** (`DATABASE_URL=postgresql://...`) alongside persistent storage for uploads.
- Set `ENVIRONMENT=production` and a strong `SECRET_KEY` so session and CSRF cookies are issued as HTTPS-only `Secure` cookies.

---

## Disclaimer

SpendSense provides general budgeting guidance and educational estimates—not professional financial, tax, or investment advice. Exchange rates are approximate static references.
