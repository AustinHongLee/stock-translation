from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DeidentifyOptions:
    mask_amounts: bool = True
    scrub_strings: bool = True


SENSITIVE_KEYS = {
    "id",
    "note",
    "memo",
    "account",
    "account_id",
    "broker",
    "email",
    "phone",
    "created_at",
    "updated_at",
}

AMOUNT_KEYWORDS = (
    "amount",
    "cost",
    "value",
    "price",
    "fee",
    "tax",
    "shares",
    "pnl",
    "dividend",
    "market_value",
    "average_cost",
)


def deidentify_payload(payload: Any, *, options: DeidentifyOptions | None = None) -> Any:
    options = options or DeidentifyOptions()
    return _deidentify(payload, key=None, options=options)


def _deidentify(value: Any, *, key: str | None, options: DeidentifyOptions) -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for child_key, child_value in value.items():
            normalized_key = str(child_key).lower()
            if normalized_key in SENSITIVE_KEYS or normalized_key.endswith("_id") and normalized_key != "stock_id":
                continue
            output[str(child_key)] = _deidentify(child_value, key=str(child_key), options=options)
        return output
    if isinstance(value, list):
        return [_deidentify(item, key=key, options=options) for item in value]
    if isinstance(value, tuple):
        return [_deidentify(item, key=key, options=options) for item in value]
    if options.mask_amounts and isinstance(value, (int, float)) and _is_amount_key(key):
        return _bucket_number(float(value))
    if options.scrub_strings and isinstance(value, str):
        return _scrub_string(value)
    return value


def _is_amount_key(key: str | None) -> bool:
    if not key:
        return False
    normalized = key.lower()
    if "percent" in normalized or "ratio" in normalized or "yield" in normalized:
        return False
    return any(token in normalized for token in AMOUNT_KEYWORDS)


def _bucket_number(value: float) -> str:
    absolute = abs(value)
    sign = "-" if value < 0 else ""
    if absolute == 0:
        return "0"
    if absolute < 1_000:
        return f"{sign}千元內"
    if absolute < 10_000:
        return f"{sign}千元級"
    if absolute < 100_000:
        return f"{sign}萬元級"
    if absolute < 1_000_000:
        return f"{sign}十萬元級"
    if absolute < 10_000_000:
        return f"{sign}百萬元級"
    return f"{sign}千萬元以上"


def _scrub_string(value: str) -> str:
    scrubbed = re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", "[email]", value)
    scrubbed = re.sub(r"09\d{2}[-\s]?\d{3}[-\s]?\d{3}", "[phone]", scrubbed)
    return scrubbed
