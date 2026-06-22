from __future__ import annotations

from typing import Any


FILTER_ALL = "all"
FILTER_STALE = "stale"
FILTER_NEAR_RESISTANCE = "near_resistance"
FILTER_NEAR_SUPPORT = "near_support"

SORT_STOCK_ID = "stock_id"
SORT_PRICE_ROWS_DESC = "price_rows_desc"
SORT_LAST_DATE_DESC = "last_date_desc"
SORT_LAST_DATE_ASC = "last_date_asc"
SORT_LEVEL_STATUS = "level_status"

_LEVEL_RANK = {
    "接近波壓": 0,
    "接近波撐": 1,
    "正常": 2,
    "資料不足": 3,
    "": 4,
}


def filter_sort_local_data_items(
    items: list[dict[str, Any]],
    *,
    filter_mode: str = FILTER_ALL,
    sort_key: str = SORT_STOCK_ID,
) -> list[dict[str, Any]]:
    """Filter and sort local-data table rows without mutating the input."""
    filtered = [dict(item) for item in items if _keep_item(item, filter_mode)]
    return sorted(filtered, key=lambda item: _sort_key(item, sort_key))


def _keep_item(item: dict[str, Any], filter_mode: str) -> bool:
    if filter_mode == FILTER_STALE:
        return _number(item.get("stale_days")) > 7
    if filter_mode == FILTER_NEAR_RESISTANCE:
        return str(item.get("sr_status") or "") == "接近波壓"
    if filter_mode == FILTER_NEAR_SUPPORT:
        return str(item.get("sr_status") or "") == "接近波撐"
    return True


def _sort_key(item: dict[str, Any], sort_key: str) -> tuple[Any, ...]:
    stock_id = str(item.get("stock_id") or "")
    if sort_key == SORT_PRICE_ROWS_DESC:
        return (-_number(item.get("price_rows")), stock_id)
    if sort_key == SORT_LAST_DATE_DESC:
        return (_invert_text(str(item.get("last_date") or "")), stock_id)
    if sort_key == SORT_LAST_DATE_ASC:
        return (str(item.get("last_date") or ""), stock_id)
    if sort_key == SORT_LEVEL_STATUS:
        status = str(item.get("sr_status") or "")
        return (_LEVEL_RANK.get(status, 4), stock_id)
    return (stock_id,)


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _invert_text(value: str) -> tuple[int, ...]:
    return tuple(-ord(ch) for ch in value)
