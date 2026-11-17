"""Pure parsers, Pydantic schemas, keyword categoriser, and merchant normalization."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Literal

from babel.numbers import get_currency_precision
from pydantic import BaseModel, Field, field_validator

from data.sample_data import CATEGORIES


class ParsedTransaction(BaseModel):
    amount: Decimal = Field(gt=0)
    amount_minor: int = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    merchant: str = Field(min_length=1, max_length=120)
    category: str
    date: str
    type: Literal["expense", "income"] = "expense"

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, v: str) -> str:
        c = v.strip().upper()
        if len(c) != 3 or not c.isalpha():
            raise ValueError("Invalid currency code")
        return c

    @field_validator("category")
    @classmethod
    def _valid_category(cls, v: str) -> str:
        if v in CATEGORIES:
            return v
        return "Other"

    @field_validator("date")
    @classmethod
    def _valid_iso_date(cls, v: str) -> str:
        date.fromisoformat(v)
        return v


class GeminiRawTransaction(BaseModel):
    amount: float | str | None = None
    currency: str | None = None
    merchant: str | None = None
    category: str | None = None
    date: str | None = None
    type: Literal["expense", "income"] = "expense"


class MoneyBuddyResult(BaseModel):
    answer: str
    next_step: str
    why: list[str]
    offline_mode: bool = False


class CategorySuggestionResult(BaseModel):
    category: str
    source: Literal["memory", "keyword", "ai"] = "keyword"
    offline_mode: bool = False


class HomeNarrativeResult(BaseModel):
    monthly_summary: str
    insights: list[dict]
    offline_mode: bool = False


class AffordabilityExplanationResult(BaseModel):
    explanation: str
    offline_mode: bool = False


CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Food & Mess": (
        "chai",
        "tea",
        "coffee",
        "mess",
        "canteen",
        "zomato",
        "swiggy",
        "instamart",
        "blinkit",
        "zepto",
        "biryani",
        "maggi",
        "lunch",
        "dinner",
        "breakfast",
        "snack",
        "pizza",
        "burger",
        "dominos",
        "kfc",
        "mcdonald",
        "starbucks",
        "cafe",
        "bakery",
        "grocery",
        "groceries",
        "trader joe",
        "carrefour",
        "tesco",
        "pret",
        "food",
        "dosa",
        "samosa",
        "thali",
    ),
    "Travel": (
        "auto",
        "rickshaw",
        "cab",
        "uber",
        "ola",
        "rapido",
        "metro",
        "bus",
        "train",
        "irctc",
        "flight",
        "petrol",
        "fuel",
        "diesel",
        "parking",
        "toll",
        "ticket",
        "commute",
    ),
    "Shopping": (
        "amazon",
        "flipkart",
        "myntra",
        "ajio",
        "meesho",
        "decathlon",
        "zara",
        "h&m",
        "uniqlo",
        "shoes",
        "shirt",
        "jeans",
        "clothes",
        "bottle",
        "electronics",
        "headphones",
        "mall",
        "shopping",
    ),
    "Education": (
        "xerox",
        "print",
        "book",
        "books",
        "textbook",
        "notebook",
        "stationery",
        "pen",
        "tuition",
        "course",
        "udemy",
        "coursera",
        "exam",
        "fee",
        "fees",
        "lab",
        "library",
        "college",
    ),
    "Bills & Recharge": (
        "jio",
        "airtel",
        "vi ",
        "vodafone",
        "bsnl",
        "recharge",
        "mobile",
        "wifi",
        "broadband",
        "internet",
        "electricity",
        "water bill",
        "gas bill",
        "bill",
        "postpaid",
        "prepaid",
        "dth",
    ),
    "Entertainment": (
        "spotify",
        "netflix",
        "prime video",
        "hotstar",
        "youtube",
        "movie",
        "cinema",
        "pvr",
        "inox",
        "bookmyshow",
        "game",
        "steam",
        "concert",
        "outing",
        "club",
        "party",
    ),
    "Rent & Hostel": (
        "hostel",
        "rent",
        "pg ",
        "laundry",
        "room",
        "deposit",
        "maintenance",
        "flat",
        "landlord",
        "utility",
    ),
    "Health": (
        "medical",
        "pharmacy",
        "apollo",
        "pharmeasy",
        "1mg",
        "medicine",
        "doctor",
        "clinic",
        "hospital",
        "chemist",
        "vitamin",
        "dental",
        "gym",
    ),
}

CURRENCY_PREFIX_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?:₹|rs\.?|inr)\s*([0-9][0-9,]*(?:\.[0-9]{1,3})?)", re.I), "INR"),
    (re.compile(r"(?:\$|usd|us\$)\s*([0-9][0-9,]*(?:\.[0-9]{1,3})?)", re.I), "USD"),
    (re.compile(r"(?:€|eur)\s*([0-9][0-9,]*(?:\.[0-9]{1,3})?)", re.I), "EUR"),
    (re.compile(r"(?:£|gbp)\s*([0-9][0-9,]*(?:\.[0-9]{1,3})?)", re.I), "GBP"),
    (re.compile(r"(?:¥|￥|jpy)\s*([0-9][0-9,]*(?:\.[0-9]{1,3})?)", re.I), "JPY"),
    (re.compile(r"(?:aed|dirham)\s*([0-9][0-9,]*(?:\.[0-9]{1,3})?)", re.I), "AED"),
    (re.compile(r"(?:sgd|s\$)\s*([0-9][0-9,]*(?:\.[0-9]{1,3})?)", re.I), "SGD"),
    (re.compile(r"(?:aud|a\$)\s*([0-9][0-9,]*(?:\.[0-9]{1,3})?)", re.I), "AUD"),
    (re.compile(r"(?:cad|c\$)\s*([0-9][0-9,]*(?:\.[0-9]{1,3})?)", re.I), "CAD"),
]

CURRENCY_SUFFIX_PATTERN = re.compile(
    r"\b([0-9][0-9,]*(?:\.[0-9]{1,3})?)\s*(inr|rs\.?|usd|eur|gbp|jpy|aed|sgd|aud|cad)\b",
    re.I,
)

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def normalize_merchant(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", (name or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def to_minor_units(amount: Decimal, currency_code: str) -> int:
    precision = get_currency_precision(currency_code)
    scale = Decimal(10) ** precision
    minor = int((amount * scale).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return minor


def categorize_by_keywords(
    text: str,
    merchant_memory: dict[str, str] | None = None,
) -> str:
    norm = normalize_merchant(text)
    if merchant_memory and norm:
        if norm in merchant_memory and merchant_memory[norm] in CATEGORIES:
            return merchant_memory[norm]
        for mem_key, mem_cat in merchant_memory.items():
            if mem_key and (mem_key in norm or norm in mem_key) and mem_cat in CATEGORIES:
                return mem_cat

    padded = f" {norm} "
    for category, words in CATEGORY_KEYWORDS.items():
        for kw in words:
            if kw in padded or kw in (text or "").lower():
                return category
    return "Other"


def _extract_date(text: str, ref_today: date) -> str:
    lower = text.lower()
    if "yesterday" in lower or "kal" in re.findall(r"\bkal\b", lower):
        return (ref_today - timedelta(days=1)).isoformat()
    if "today" in lower or "aaj" in re.findall(r"\baaj\b", lower):
        return ref_today.isoformat()

    iso_m = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", text)
    if iso_m:
        try:
            return date(int(iso_m.group(1)), int(iso_m.group(2)), int(iso_m.group(3))).isoformat()
        except ValueError:
            pass

    dmy_m = re.search(r"\b(\d{1,2})[-/]([a-zA-Z]{3,4})(?:[-/](\d{2,4}))?\b", text)
    if dmy_m:
        day_num = int(dmy_m.group(1))
        mon_num = MONTH_MAP.get(dmy_m.group(2).lower())
        if mon_num:
            yr_raw = dmy_m.group(3)
            yr = int(yr_raw) if yr_raw else ref_today.year
            if yr < 100:
                yr += 2000
            try:
                return date(yr, mon_num, day_num).isoformat()
            except ValueError:
                pass

    slash_m = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2}|\d{2})\b", text)
    if slash_m:
        d_num, m_num, y_raw = int(slash_m.group(1)), int(slash_m.group(2)), int(slash_m.group(3))
        if y_raw < 100:
            y_raw += 2000
        try:
            return date(y_raw, m_num, d_num).isoformat()
        except ValueError:
            pass

    return ref_today.isoformat()


def _extract_type(text: str) -> Literal["expense", "income"]:
    lower = text.lower()
    if re.search(r"\b(credited|received|salary|allowance|refund|cashback|deposited)\b", lower):
        if not re.search(r"\b(debited|paid|spent|purchase)\b", lower):
            return "income"
    return "expense"


def _extract_merchant(text: str, raw_amount_span: tuple[int, int] | None = None) -> str:
    # Prefer bank/UPI SMS "to <merchant>" or "at <merchant>" or "from <sender>"
    sms_m = re.search(
        r"\b(?:to|at|towards|for)\s+([A-Za-z0-9&'._\- ]{2,48}?)(?=\s+(?:on\b|via\b|ref\b|upi\b|avl\b|bal\b|info\b)|[.,;!\n]|$)",
        text,
        re.I,
    )
    if sms_m:
        cand = re.sub(r"\s+", " ", sms_m.group(1)).strip(" -.,")
        if cand and not cand.lower().startswith(("a/c", "ac ", "account")):
            return cand[:80]

    # Strip currency + amount + common filler words for natural text ("chai 20", "auto 80 yesterday")
    cleaned = text
    if raw_amount_span:
        cleaned = cleaned[: raw_amount_span[0]] + " " + cleaned[raw_amount_span[1] :]
    cleaned = re.sub(
        r"\b(today|yesterday|aaj|kal|rs\.?|inr|usd|eur|gbp|jpy|debited|credited|spent|paid|from|a/c|account|via|upi|on|at|to)\b",
        " ",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(r"[₹$€£¥*#:/]+", " ", cleaned)
    cleaned = re.sub(r"\b\d{1,2}[-/](?:[A-Za-z]{3,4}|\d{1,2})(?:[-/]\d{2,4})?\b", " ", cleaned)
    cleaned = re.sub(r"\b\d{4,}\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -.,")
    if cleaned:
        return cleaned[:80].title() if cleaned.islower() else cleaned[:80]
    return "Quick expense"


def parse_transaction_text(
    text: str,
    *,
    default_currency: str = "INR",
    today: date | None = None,
    merchant_memory: dict[str, str] | None = None,
) -> ParsedTransaction:
    """Parse an SMS alert or natural shorthand like 'chai 20' / 'auto 80 yesterday'."""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("Please type an expense or paste a bank/UPI SMS alert.")

    ref_today = today or date.today()
    detected_currency: str | None = None
    amount_dec: Decimal | None = None
    match_span: tuple[int, int] | None = None

    for pat, code in CURRENCY_PREFIX_PATTERNS:
        m = pat.search(raw)
        if m:
            try:
                val = Decimal(m.group(1).replace(",", ""))
                if val > 0:
                    amount_dec = val
                    detected_currency = code
                    match_span = m.span()
                    break
            except InvalidOperation:
                continue

    if amount_dec is None:
        m_suf = CURRENCY_SUFFIX_PATTERN.search(raw)
        if m_suf:
            code_raw = m_suf.group(2).upper().rstrip(".")
            code_map = {"RS": "INR"}
            try:
                val = Decimal(m_suf.group(1).replace(",", ""))
                if val > 0:
                    amount_dec = val
                    detected_currency = code_map.get(code_raw, code_raw)
                    match_span = m_suf.span()
            except InvalidOperation:
                pass

    if amount_dec is None:
        # Ignore masked account numbers (**4192, XX1234) and date parts (17-Nov, 2026-11-17)
        scrubbed = re.sub(r"(?:\*\*|xx)\d+", " ", raw, flags=re.I)
        scrubbed = re.sub(r"\b20\d{2}-\d{1,2}-\d{1,2}\b", " ", scrubbed)
        scrubbed = re.sub(r"\b\d{1,2}[-/](?:[A-Za-z]{3,4}|\d{1,2})(?:[-/]\d{2,4})?\b", " ", scrubbed)
        bare_m = re.search(r"\b([0-9][0-9,]*(?:\.[0-9]{1,3})?)\b", scrubbed)
        if bare_m:
            try:
                val = Decimal(bare_m.group(1).replace(",", ""))
                if val > 0:
                    amount_dec = val
                    detected_currency = default_currency.upper()
                    match_span = bare_m.span()
            except InvalidOperation:
                pass

    if amount_dec is None or amount_dec <= 0:
        raise ValueError(
            "Could not find an amount in that text. Try something like 'chai 20' or paste an SMS with an amount."
        )

    final_currency = (detected_currency or default_currency or "INR").upper()
    merchant = _extract_merchant(raw, match_span)
    tx_date = _extract_date(raw, ref_today)
    tx_type = _extract_type(raw)
    category = categorize_by_keywords(f"{merchant} {raw}", merchant_memory=merchant_memory)
    amount_minor = to_minor_units(amount_dec, final_currency)
    if amount_minor <= 0:
        raise ValueError("Parsed amount must be greater than zero.")

    return ParsedTransaction(
        amount=amount_dec,
        amount_minor=amount_minor,
        currency=final_currency,
        merchant=merchant,
        category=category,
        date=tx_date,
        type=tx_type,
    )
