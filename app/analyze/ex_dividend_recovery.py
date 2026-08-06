"""歷年填權息（實際上只統計「填息」）：除息後股價回到除息前收盤的歷史行為。

純函數、零 I/O。輸入本地日線與股利記錄，只取 TWT49U 除權息計算結果
（source=TWSE_TWT49U：board_date=除息日、cash_dividend=息值）當事件來源——
公告口徑（t187ap45）的 board_date 是董事會日期，不能當除息日用。

紅線：只描述過去每次除息「有沒有回到基準價、花了幾個交易日」的事實，
不推論未來、不當買賣依據；樣本不足要老實說。
"""
from __future__ import annotations

from datetime import date, timedelta
from statistics import median
from typing import Any

from app.analyze.dividends import SOURCE_EX_DIVIDEND

DEFAULT_YEARS = 5
FILL_WINDOW_CALENDAR_DAYS = 365  # 超過一年未填息 → 視為該次未填（終局）
BASE_PRICE_MAX_GAP_DAYS = 15  # 除息前基準價距除息日太遠（長停牌）→ 該事件不列入統計
MIN_EVENT_PRICE_ROWS = 3  # 事件窗口內價格筆數太少 → 不列入統計
MIN_EVENTS_FOR_STATS = 2

DISCLAIMER = "填息統計只整理過去的價格行為，不代表未來會重演，不預測股價、不構成投資建議。"


def build_ex_dividend_recovery(
    prices: list[Any],
    dividends: list[Any],
    *,
    today: date,
    years: int = DEFAULT_YEARS,
) -> dict[str, Any]:
    """回傳歷年填息事件與統計；資料不足時 available=False 並說明原因。"""
    series = _price_series(prices)
    events_in = _ex_dividend_events(dividends, today=today, years=years)
    if not events_in:
        return _unavailable("近年沒有可用的除息紀錄（需要含除息日的 TWT49U 資料）。")
    if len(series) < MIN_EVENT_PRICE_ROWS:
        return _unavailable("本地日線不足，無法對照除息前後價格。")

    dates = [row[0] for row in series]
    events: list[dict[str, Any]] = []
    skipped_events = 0
    for index, (ex_date, cash) in enumerate(events_in):
        next_ex = events_in[index + 1][0] if index + 1 < len(events_in) else None
        event = _assess_event(
            series,
            dates,
            ex_date=ex_date,
            cash_dividend=cash,
            next_ex_date=next_ex,
            today=today,
        )
        if event is None:
            skipped_events += 1
            continue
        events.append(event)

    if not events:
        return _unavailable("除息事件都缺少對應的價格資料（可能停牌或日線缺洞），先補資料再看。")

    settled = [event for event in events if event["filled"] is not None]
    filled = [event for event in events if event["filled"] is True]
    fill_days = [event["fill_trading_days"] for event in filled]
    ongoing = next((event for event in events if event["filled"] is None), None)

    stats = {
        "events_count": len(settled),
        "filled_count": len(filled),
        "fill_rate_percent": (
            round(len(filled) / len(settled) * 100, 1) if settled else None
        ),
        "median_fill_trading_days": int(median(fill_days)) if fill_days else None,
        "avg_fill_trading_days": round(sum(fill_days) / len(fill_days), 1) if fill_days else None,
        "skipped_events": skipped_events,
    }

    return {
        "available": True,
        "years": years,
        "events": events,
        "stats": stats,
        "ongoing": ongoing,
        "note": _note(stats, ongoing, years),
        "disclaimer": DISCLAIMER,
    }


def _assess_event(
    series: list[tuple[date, float]],
    dates: list[date],
    *,
    ex_date: date,
    cash_dividend: float,
    next_ex_date: date | None,
    today: date,
) -> dict[str, Any] | None:
    base_index = _last_index_before(dates, ex_date)
    if base_index < 0:
        return None
    base_date, base_close = series[base_index]
    if (ex_date - base_date).days > BASE_PRICE_MAX_GAP_DAYS or base_close <= 0:
        return None

    window_end = ex_date + timedelta(days=FILL_WINDOW_CALENDAR_DAYS)
    truncated_by_next = next_ex_date is not None and next_ex_date <= window_end
    if truncated_by_next and next_ex_date is not None:
        window_end = next_ex_date - timedelta(days=1)

    window = [
        (idx, row)
        for idx, row in enumerate(series)
        if ex_date <= row[0] <= window_end
    ]
    if len(window) < MIN_EVENT_PRICE_ROWS and window_end < today:
        return None

    fill_entry = next((item for item in window if item[1][1] >= base_close), None)
    window_closed = window_end < today

    filled: bool | None
    fill_date: date | None = None
    fill_trading_days: int | None = None
    current_gap_percent: float | None = None
    if fill_entry is not None:
        filled = True
        fill_index, (fill_date, _close) = fill_entry
        first_index = window[0][0]
        fill_trading_days = fill_index - first_index + 1
    elif window_closed:
        filled = False
    else:
        filled = None  # 進行中：窗口未結束，還不能下定論
        latest_close = window[-1][1][1] if window else None
        if latest_close is not None and base_close > 0:
            current_gap_percent = round((base_close - latest_close) / base_close * 100, 2)

    return {
        "ex_date": ex_date.isoformat(),
        "cash_dividend": round(float(cash_dividend), 4),
        "base_date": base_date.isoformat(),
        "base_close": round(float(base_close), 4),
        "filled": filled,
        "fill_date": fill_date.isoformat() if fill_date else None,
        "fill_trading_days": fill_trading_days,
        "window_truncated_by_next_ex": bool(truncated_by_next),
        "current_gap_percent": current_gap_percent,
    }


def _note(stats: dict[str, Any], ongoing: dict[str, Any] | None, years: int) -> str:
    parts: list[str] = []
    settled = int(stats.get("events_count") or 0)
    filled = int(stats.get("filled_count") or 0)
    if settled >= MIN_EVENTS_FOR_STATS:
        sentence = f"近 {years} 年可判定的除息共 {settled} 次，其中 {filled} 次回到除息前價位"
        median_days = stats.get("median_fill_trading_days")
        if filled and median_days is not None:
            sentence += f"（填息中位約 {median_days} 個交易日）"
        parts.append(sentence + "。")
    elif settled:
        parts.append(f"可判定的除息只有 {settled} 次，統計參考性低。")
    if ongoing is not None:
        gap = ongoing.get("current_gap_percent")
        if gap is None or gap <= 0:
            parts.append("最近一次除息的觀察期還在進行中。")
        else:
            parts.append(
                f"最近一次除息（{ongoing['ex_date']}）還沒回到除息前價位，目前差約 {gap:.1f}%。"
            )
    if int(stats.get("skipped_events") or 0):
        parts.append("部分較早的除息因價格資料不足未列入。")
    return "".join(parts)


def _ex_dividend_events(
    dividends: list[Any],
    *,
    today: date,
    years: int,
) -> list[tuple[date, float]]:
    horizon_start = date(today.year - years, today.month, min(today.day, 28))
    events: list[tuple[date, float]] = []
    seen: set[date] = set()
    for record in dividends or []:
        source = str(_field(record, "source") or "")
        if source != SOURCE_EX_DIVIDEND:
            continue
        ex_date = _as_date(_field(record, "board_date"))
        cash = _number(_field(record, "cash_dividend")) or 0.0
        if ex_date is None or cash <= 0:
            continue
        if not horizon_start <= ex_date <= today:
            continue
        if ex_date in seen:
            continue
        seen.add(ex_date)
        events.append((ex_date, cash))
    return sorted(events)


def _price_series(prices: list[Any]) -> list[tuple[date, float]]:
    rows: list[tuple[date, float]] = []
    for item in prices or []:
        day = _as_date(_field(item, "date"))
        close = _number(_field(item, "close"))
        if day is None or close is None or close <= 0:
            continue
        rows.append((day, close))
    rows.sort(key=lambda row: row[0])
    return rows


def _last_index_before(dates: list[date], target: date) -> int:
    """回傳嚴格早於 target 的最後一個索引；沒有回 -1。"""
    low, high = 0, len(dates) - 1
    result = -1
    while low <= high:
        mid = (low + high) // 2
        if dates[mid] < target:
            result = mid
            low = mid + 1
        else:
            high = mid - 1
    return result


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "reason": reason,
        "events": [],
        "stats": None,
        "ongoing": None,
        "note": reason,
        "disclaimer": DISCLAIMER,
    }


def _field(item: Any, key: str) -> Any:
    if item is None:
        return None
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _as_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number
