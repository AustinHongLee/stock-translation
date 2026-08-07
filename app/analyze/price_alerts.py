"""到價提醒（收盤檢查版）：判定與白話文案的純函數。

刻意只用「每日收盤價」檢查（docs/06 O1：不做即時報價與盤中推播）——
收盤資料更新後，若收盤價到達使用者自設的價位，就在首頁與個股頁提醒一次。
文案中性：只說「已到你設定的價位」，不說該買該賣、不評好壞。
"""
from __future__ import annotations

from typing import Any

DIRECTION_ABOVE = "above"
DIRECTION_BELOW = "below"
DIRECTIONS = (DIRECTION_ABOVE, DIRECTION_BELOW)
RECENT_TRIGGER_KEEP_DAYS = 7  # 觸發後在首頁保留幾天（之後仍可在個股頁看歷史）


def alert_hits(direction: str, target_price: float, close: float) -> bool:
    """收盤價是否到達提醒條件（含等於）。未知方向一律 False。"""
    if close is None or target_price is None:
        return False
    if direction == DIRECTION_ABOVE:
        return close >= target_price
    if direction == DIRECTION_BELOW:
        return close <= target_price
    return False


def alert_line(alert: dict[str, Any], *, name: str | None = None) -> str:
    """觸發後顯示的白話一句（中性、不建議）。"""
    label = name or str(alert.get("stock_id") or "")
    direction = str(alert.get("direction") or "")
    price = _number(alert.get("price"))
    close = _number(alert.get("triggered_close"))
    day = str(alert.get("triggered_date") or "")
    side = "以上" if direction == DIRECTION_ABOVE else "以下"
    parts = [f"⚑ {label} 收盤 {_fmt(close)}，已到你設定的 {_fmt(price)} {side}"]
    if day:
        parts.append(f"（{day}）")
    return "".join(parts)


def normalize_direction(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text if text in DIRECTIONS else None


def _fmt(value: float | None) -> str:
    if value is None:
        return "--"
    text = f"{value:,.2f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
