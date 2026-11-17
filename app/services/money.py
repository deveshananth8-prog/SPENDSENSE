"""Pure money formatting and currency catalog utilities.

No float is ever used for monetary storage or arithmetic.
"""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from babel.numbers import format_currency, get_currency_precision

RATES_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "rates.json"


def load_currency_catalog() -> dict[str, Any]:
    with RATES_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def get_currency_list() -> list[dict[str, str]]:
    catalog = load_currency_catalog()
    currencies = catalog.get("currencies", {})
    return [
        {
            "code": code,
            "name": meta["name"],
            "symbol": meta["symbol"],
            "locale": meta["locale"],
            "rate_from_inr": meta["rate_from_inr"],
            "precision": str(get_currency_precision(code)),
        }
        for code, meta in currencies.items()
    ]


def minor_to_decimal(amount_minor: int, currency_code: str) -> Decimal:
    precision = get_currency_precision(currency_code)
    scale = Decimal(10) ** precision
    quant = Decimal(10) ** (-precision) if precision > 0 else Decimal(1)
    return (Decimal(amount_minor) / scale).quantize(quant, rounding=ROUND_HALF_UP)


def format_money(amount_minor: int, currency_code: str = "INR", locale: str = "en_IN") -> str:
    """Format an integer minor-unit amount using Babel and ROUND_HALF_UP.

    Examples:
      format_money(12500000, "INR", "en_IN") -> "₹1,25,000.00"
      format_money(12500000, "USD", "en_US") -> "$125,000.00"
      format_money(125000, "JPY", "ja_JP")   -> "￥125,000"
    """
    precision = get_currency_precision(currency_code)
    value = minor_to_decimal(amount_minor, currency_code)
    formatted = format_currency(
        value,
        currency_code,
        locale=locale,
        currency_digits=True,
    )
    # Strip trailing all-zero fractional part only? Keep standard Babel precision
    # so JPY has 0 decimals, KWD has 3, USD/INR have 2.
    if precision == 0 and "." in formatted:
        formatted = formatted.split(".")[0]
    return formatted
