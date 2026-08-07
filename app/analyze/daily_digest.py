"""首頁「今日異動」摘要：把自選股最近交易日的變化整理成幾句白話。

純函數、零 I/O：輸入是 watchlist payload 的 items 與各檔近幾日法人買賣超，
輸出一個 digest dict。只描述已發生的事實（漲跌、連續買賣超、資料狀態），
不預測股價、不給買賣建議、不用多空煽動字眼。
"""
from __future__ import annotations

from datetime import date
from typing import Any

MOVER_THRESHOLD_PERCENT = 2.0  # 單日漲跌幅絕對值達此門檻才算「有異動」
MOVER_LIMIT = 3
CHIPS_STREAK_MIN_DAYS = 3  # 連續同向買/賣超達此天數才值得寫進摘要
CHIPS_LINE_LIMIT = 3
STALE_DAY_GATE = 10

DISCLAIMER = "只整理本地已同步資料的事實，不預測股價、不構成投資建議。"


def build_daily_digest(
    items: list[dict[str, Any]],
    chips_map: dict[str, list[Any]] | None = None,
    *,
    today: date | None = None,
    alert_lines: list[str] | None = None,
) -> dict[str, Any] | None:
    """由自選股 items（含 board）、法人資料與到價提醒組出首頁摘要。

    無自選股且無提醒 → None；只有提醒（提醒的股票不一定在自選）也要能顯示。
    """
    alert_lines = list(alert_lines or [])
    if not items:
        if not alert_lines:
            return None
        return {
            "date": None,
            "trading_summary": "",
            "movers": [],
            "chips_lines": [],
            "attention": [],
            "quiet": False,
            "alert_lines": alert_lines,
            "headline": alert_lines[0],
            "disclaimer": DISCLAIMER,
        }
    chips_map = chips_map or {}

    rows = [_digest_row(item) for item in items]
    data_date = max((row["date"] for row in rows if row["date"]), default=None)

    up = sum(1 for row in rows if row["change_percent"] is not None and row["change_percent"] > 0)
    down = sum(1 for row in rows if row["change_percent"] is not None and row["change_percent"] < 0)
    known = [row for row in rows if row["change_percent"] is not None]
    flat = len(known) - up - down
    no_data = len(rows) - len(known)

    movers = sorted(
        (row for row in known if abs(row["change_percent"]) >= MOVER_THRESHOLD_PERCENT),
        key=lambda row: abs(row["change_percent"]),
        reverse=True,
    )[:MOVER_LIMIT]

    chips_lines = _chips_lines(rows, chips_map)
    attention = _attention_lines(rows, no_data)
    quiet = bool(known) and not movers

    summary_parts = [f"自選 {len(rows)} 檔"]
    if known:
        summary_parts.append(f"{up} 漲 {down} 跌 {flat} 平")
    if no_data:
        summary_parts.append(f"{no_data} 檔無最新資料")
    trading_summary = "：".join([summary_parts[0], "、".join(summary_parts[1:])]) + "。" if len(summary_parts) > 1 else summary_parts[0] + "。"

    return {
        "date": data_date,
        "trading_summary": trading_summary,
        "movers": [
            {
                "stock_id": row["stock_id"],
                "name": row["name"],
                "close": row["close"],
                "change_percent": row["change_percent"],
                "note": row["level_note"],
            }
            for row in movers
        ],
        "chips_lines": chips_lines,
        "attention": attention,
        "quiet": quiet,
        "alert_lines": alert_lines,
        "headline": _headline(movers, chips_lines, quiet, known),
        "disclaimer": DISCLAIMER,
    }


def _digest_row(item: dict[str, Any]) -> dict[str, Any]:
    board = item.get("board") or {}
    latest = board.get("latest") or {}
    data = board.get("data") or {}
    level = board.get("level") or {}
    profile = item.get("profile") or {}
    level_status = str(level.get("status") or "")
    return {
        "stock_id": str(item.get("stock_id") or ""),
        "name": str(board.get("name") or profile.get("short_name") or item.get("stock_id") or ""),
        "close": latest.get("close"),
        "change_percent": _number(latest.get("change_percent")),
        "date": str(latest.get("date") or "") or None,
        "stale_days": _int(data.get("stale_days")),
        "level_note": level_status if level_status in {"接近波壓", "接近波撐"} else "",
    }


def _chips_lines(rows: list[dict[str, Any]], chips_map: dict[str, list[Any]]) -> list[str]:
    """連續同向買/賣超達門檻的檔案，寫成中性一句話；外資優先於三大法人合計。"""
    candidates: list[tuple[int, str]] = []
    for row in rows:
        trades = chips_map.get(row["stock_id"]) or []
        if not trades:
            continue
        ordered = sorted(trades, key=lambda item: _trade_date(item), reverse=True)
        foreign_streak, foreign_side = _streak(ordered, "foreign_net")
        total_streak, total_side = _streak(ordered, "total_net")
        if foreign_streak >= CHIPS_STREAK_MIN_DAYS:
            candidates.append(
                (foreign_streak, f"外資連 {foreign_streak} 天{foreign_side} {row['name']}")
            )
        elif total_streak >= CHIPS_STREAK_MIN_DAYS:
            candidates.append(
                (total_streak, f"三大法人連 {total_streak} 天{total_side} {row['name']}")
            )
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return [text for _days, text in candidates[:CHIPS_LINE_LIMIT]]


def _streak(ordered_trades: list[Any], field: str) -> tuple[int, str]:
    """由最新往回數連續同向天數。回傳 (天數, '買超'/'賣超')；無資料回 (0, '')。"""
    direction = 0
    count = 0
    for trade in ordered_trades:
        value = _number(_field(trade, field))
        if value is None or value == 0:
            break
        side = 1 if value > 0 else -1
        if direction == 0:
            direction = side
        if side != direction:
            break
        count += 1
    if count == 0:
        return 0, ""
    return count, "買超" if direction > 0 else "賣超"


def _attention_lines(rows: list[dict[str, Any]], no_data: int) -> list[str]:
    lines: list[str] = []
    stale = sum(1 for row in rows if row["stale_days"] is not None and row["stale_days"] > STALE_DAY_GATE)
    if stale:
        lines.append(f"{stale} 檔本地資料日期偏舊，先同步再看。")
    if no_data:
        lines.append(f"{no_data} 檔還沒有本地日線，可先按同步。")
    return lines


def _headline(
    movers: list[dict[str, Any]],
    chips_lines: list[str],
    quiet: bool,
    known: list[dict[str, Any]],
) -> str:
    parts: list[str] = []
    if movers:
        top = movers[0]
        parts.append(f"{top['name']} {_signed_percent(top['change_percent'])} 變化最大")
    elif quiet:
        parts.append(f"自選股相對平靜（漲跌都在 ±{MOVER_THRESHOLD_PERCENT:g}% 內）")
    if chips_lines:
        parts.append(chips_lines[0])
    if not parts:
        if not known:
            return "自選股還沒有可比較的最新資料，先同步一次。"
        return "自選股資料已就緒，可逐檔查看。"
    return "；".join(parts) + "。"


def _signed_percent(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value:+.2f}%"


def _field(item: Any, key: str) -> Any:
    if item is None:
        return None
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _trade_date(item: Any) -> str:
    value = _field(item, "date")
    if isinstance(value, date):
        return value.isoformat()
    return str(value or "")


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
