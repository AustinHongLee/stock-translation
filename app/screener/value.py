from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Protocol

from app.runtime_paths import data_path
from app.analyze.suitability import assess_valuation_suitability
from app.models import DailyPrice, DividendRecord, StockProfile

DEFAULT_SCREENER_PATH = data_path("value_screener.json", writable=True)
TARGET_YIELDS = {
    "cheap": 6.25,
    "fair": 5.0,
    "expensive": 3.125,
}


class ValueScreenerClient(Protocol):
    last_warnings: list[str]

    def fetch_listed_profiles(self) -> list[StockProfile]: ...

    def fetch_latest_all_prices(self) -> list[DailyPrice]: ...

    def fetch_all_dividend_records(self) -> list[DividendRecord]: ...

    def fetch_all_historical_dividend_records(
        self,
        start_date: date,
        end_date: date,
    ) -> list[DividendRecord]: ...


@dataclass(frozen=True, slots=True)
class ValueScreenerResult:
    output_path: Path
    rows: int
    generated_at: datetime
    source_start_date: date
    source_end_date: date
    warnings: list[str]


def refresh_value_screener(
    client: ValueScreenerClient,
    *,
    output_path: Path = DEFAULT_SCREENER_PATH,
    today: date | None = None,
    dividend_years: int = 5,
    fetch_years: int = 6,
) -> ValueScreenerResult:
    today = today or date.today()
    source_start_date = date(today.year - fetch_years + 1, 1, 1)
    source_end_date = today

    profiles = client.fetch_listed_profiles()
    prices = client.fetch_latest_all_prices()
    announced_dividends = client.fetch_all_dividend_records()
    historical_dividends = client.fetch_all_historical_dividend_records(
        source_start_date,
        source_end_date,
    )
    warnings = list(getattr(client, "last_warnings", []))

    payload = build_value_screener_payload(
        profiles=profiles,
        prices=prices,
        dividends=announced_dividends + historical_dividends,
        generated_at=datetime.now(timezone.utc),
        source_start_date=source_start_date,
        source_end_date=source_end_date,
        dividend_years=dividend_years,
        warnings=warnings,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return ValueScreenerResult(
        output_path=output_path,
        rows=len(payload["items"]),
        generated_at=datetime.fromisoformat(str(payload["generated_at"])),
        source_start_date=source_start_date,
        source_end_date=source_end_date,
        warnings=warnings,
    )


def build_value_screener_payload(
    *,
    profiles: list[StockProfile],
    prices: list[DailyPrice],
    dividends: list[DividendRecord],
    generated_at: datetime,
    source_start_date: date,
    source_end_date: date,
    dividend_years: int = 5,
    warnings: list[str] | None = None,
    today: date | None = None,
) -> dict[str, object]:
    today = today or source_end_date or date.today()
    profiles_by_id = {item.stock_id: item for item in profiles}
    prices_by_id = {item.stock_id: item for item in prices if item.close > 0}
    dividends_by_stock = _dividends_by_stock(_dedupe_dividend_records(dividends))

    items = []
    for stock_id, price in prices_by_id.items():
        profile = profiles_by_id.get(stock_id)
        if profile is None:
            continue
        stock_dividends = dividends_by_stock.get(stock_id, [])
        annual_cash_by_year = _annual_cash_dividends_by_year(stock_dividends)
        annual_values = _recent_annual_cash_values(annual_cash_by_year, dividend_years)
        average_cash = sum(annual_values) / len(annual_values) if annual_values else None
        cheap_price = _estimate_price(average_cash, TARGET_YIELDS["cheap"])
        fair_price = _estimate_price(average_cash, TARGET_YIELDS["fair"])
        expensive_price = _estimate_price(average_cash, TARGET_YIELDS["expensive"])
        difference = price.close - cheap_price if cheap_price is not None else None
        difference_percent = (
            (difference / cheap_price) * 100
            if difference is not None and cheap_price
            else None
        )
        previous_close = (
            price.close - price.change
            if price.change is not None
            else None
        )
        day_change_percent = (
            (price.change / previous_close) * 100
            if price.change is not None and previous_close and previous_close > 0
            else None
        )
        current_yield_percent = (
            (average_cash / price.close) * 100
            if average_cash is not None and average_cash > 0 and price.close > 0
            else None
        )
        data_years = len(annual_values)
        confidence, confidence_notes = _confidence(
            average_cash=average_cash,
            current_price=price.close,
            data_years=data_years,
            target_years=dividend_years,
            profile=profile,
            as_of_date=price.date,
        )
        # --- 估價適用性（僅用股利與基本資料，無財報）---
        suitability = assess_valuation_suitability(
            dividends=stock_dividends,
            financials=None,
            market=None,
            latest_close=price.close,
            profile=profile,
            as_of_date=today,
        )
        yield_trap, yield_trap_reason = _yield_trap_check(annual_values, profile)

        items.append(
            {
                "stock_id": stock_id,
                "name": profile.name,
                "short_name": profile.short_name,
                "market": profile.market,
                "price_date": price.date.isoformat(),
                "current_price": price.close,
                "previous_close": previous_close,
                "day_change": price.change,
                "day_change_percent": day_change_percent,
                "volume": price.volume,
                "average_cash_dividend": average_cash,
                "current_yield_percent": current_yield_percent,
                "dividend_years": sorted(annual_cash_by_year, reverse=True)[:dividend_years],
                "annual_cash_by_year": {
                    str(year): round(annual_cash_by_year[year], 4)
                    for year in sorted(annual_cash_by_year, reverse=True)[:dividend_years]
                },
                "data_years": data_years,
                "cheap_price": cheap_price,
                "fair_price": fair_price,
                "expensive_price": expensive_price,
                "difference": difference,
                "difference_percent": difference_percent,
                "status": _status(average_cash, data_years, dividend_years),
                "confidence": confidence,
                "confidence_label": _confidence_label(confidence),
                "confidence_notes": confidence_notes,
                # --- Phase 3 新增欄位 ---
                "suitability_state": suitability.state,
                "company_type": suitability.company_type,
                "company_type_label": suitability.company_type_label,
                "suitability_reasons": suitability.reasons,
                "yield_trap": yield_trap,
                "yield_trap_reason": yield_trap_reason,
            }
        )

    items.sort(key=_sort_key)
    available = [item for item in items if item["difference"] is not None]

    # 主榜：只放高信心（applicable）
    below_cheap_high_conf = [
        item for item in available
        if float(item["difference"]) <= 0 and item.get("suitability_state") == "applicable"
    ]
    below_cheap_low_conf = [
        item for item in available
        if float(item["difference"]) <= 0 and item.get("suitability_state") != "applicable"
    ]
    below_cheap = below_cheap_high_conf + below_cheap_low_conf  # 合計（backward compat）
    near_cheap = [
        item
        for item in available
        if 0 < float(item["difference_percent"] or 0) <= 10
        and item.get("suitability_state") == "applicable"
    ]
    day_changed = [item for item in items if item["day_change_percent"] is not None]
    gainers = [item for item in day_changed if float(item["day_change_percent"]) > 0]
    losers = [item for item in day_changed if float(item["day_change_percent"]) < 0]

    yield_available = [item for item in items if item["current_yield_percent"] is not None]
    yield_normal = [
        item for item in yield_available
        if not item.get("yield_trap") and item.get("suitability_state") == "applicable"
    ]
    yield_trap_list = [item for item in yield_available if item.get("yield_trap")]

    return {
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "method": "batch_twse_radar_center",
        "source": {
            "prices": "TWSE STOCK_DAY_ALL",
            "profiles": "TWSE t187ap03_L",
            "announced_dividends": "TWSE t187ap45_L",
            "historical_dividends": "TWSE TWT49U",
            "source_start_date": source_start_date.isoformat(),
            "source_end_date": source_end_date.isoformat(),
        },
        "targets": TARGET_YIELDS,
        "summary": {
            "rows": len(items),
            "available_rows": len(available),
            "below_cheap_rows": len(below_cheap),
            "below_cheap_high_conf_rows": len(below_cheap_high_conf),
            "below_cheap_low_conf_rows": len(below_cheap_low_conf),
            "near_cheap_rows": len(near_cheap),
            "day_changed_rows": len(day_changed),
            "gainers_rows": len(gainers),
            "losers_rows": len(losers),
            "yield_available_rows": len(yield_available),
            "yield_normal_rows": len(yield_normal),
            "yield_trap_rows": len(yield_trap_list),
            "complete_rows": sum(1 for item in available if int(item["data_years"]) >= dividend_years),
            "low_confidence_rows": sum(1 for item in available if item.get("confidence") == "low"),
            "excluded_low_confidence": len(below_cheap_low_conf),
            "warnings": warnings or [],
        },
        # --- 分區陣列（Phase 3）---
        "below_cheap_high_conf": below_cheap_high_conf[:50],
        "below_cheap_low_conf": below_cheap_low_conf[:30],
        "yield_normal": sorted(yield_normal, key=lambda x: -(x["current_yield_percent"] or 0))[:50],
        "yield_trap": sorted(yield_trap_list, key=lambda x: -(x["current_yield_percent"] or 0))[:20],
        "gainers": sorted(gainers, key=lambda x: -float(x["day_change_percent"] or 0))[:50],
        "losers": sorted(losers, key=lambda x: float(x["day_change_percent"] or 0))[:50],
        "items": items,
    }


def load_value_screener(path: Path = DEFAULT_SCREENER_PATH) -> dict[str, object]:
    if not path.is_file() and path.name:
        fallback = data_path(path.name)
        if fallback.is_file():
            path = fallback
    if not path.is_file():
        return {
            "generated_at": None,
            "method": "batch_twse_radar_center",
            "source": {},
            "targets": TARGET_YIELDS,
            "summary": {
                "rows": 0,
                "available_rows": 0,
                "below_cheap_rows": 0,
                "near_cheap_rows": 0,
                "day_changed_rows": 0,
                "gainers_rows": 0,
                "losers_rows": 0,
                "yield_available_rows": 0,
                "complete_rows": 0,
                "low_confidence_rows": 0,
                "warnings": ["尚未更新雷達中心。"],
            },
            "items": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def _yield_trap_check(
    recent_values: list[float],
    profile: StockProfile | None,
) -> tuple[bool, str]:
    """偵測殖利率陷阱（screener 層級，僅用股利資料）。

    Returns (is_trap, reason_text).
    限制：無 EPS / 60 日歷史價，只能偵測「一次性高股利」陷阱。
    """
    positive = [v for v in recent_values if v > 0]
    if len(positive) >= 3:
        median = statistics.median(positive)
        if median > 0 and max(positive) > median * 2.0:
            return True, "one_off_dividend"
    # ETF 不屬於陷阱（另有說明）
    if profile is not None:
        sid = (profile.stock_id or "").strip()
        if sid.startswith("00") and len(sid) >= 4:
            return False, ""
    return False, ""


def _sort_key(item: dict[str, object]) -> tuple[int, float, str]:
    difference_percent = item.get("difference_percent")
    if difference_percent is None:
        return (1, 0.0, str(item.get("stock_id", "")))
    return (0, float(difference_percent), str(item.get("stock_id", "")))


def _estimate_price(average_cash: float | None, target_yield_percent: float) -> float | None:
    if average_cash is None or average_cash <= 0 or target_yield_percent <= 0:
        return None
    return average_cash / (target_yield_percent / 100)


def _status(average_cash: float | None, data_years: int, target_years: int) -> str:
    if average_cash is None:
        return "資料不足"
    if average_cash <= 0:
        return "股利為 0"
    if data_years >= target_years:
        return "5 年資料"
    return f"{data_years} 年資料"


def _confidence(
    *,
    average_cash: float | None,
    current_price: float,
    data_years: int,
    target_years: int,
    profile: StockProfile,
    as_of_date: date,
) -> tuple[str, list[str]]:
    notes: list[str] = []
    confidence = "medium" if average_cash is not None else "low"
    if average_cash is None or average_cash <= 0:
        return "low", ["缺少可年化股利。"]

    if data_years < 3:
        confidence = "low"
        notes.append(f"只有 {data_years} 年股利。")
    elif data_years < target_years:
        confidence = "medium"
        notes.append(f"只有 {data_years} 年股利，非完整 {target_years} 年。")
    else:
        confidence = "high"

    if profile.listed_date is not None and (as_of_date - profile.listed_date).days < 365 * 3:
        confidence = "low"
        notes.append("上市未滿 3 年。")

    current_yield = (average_cash / current_price) * 100 if current_price > 0 else None
    if current_yield is not None and current_yield < 1:
        confidence = "low"
        notes.append("估計殖利率低於 1%。")
    return confidence, notes


def _confidence_label(confidence: str) -> str:
    if confidence == "high":
        return "信心較高"
    if confidence == "low":
        return "低信心"
    return "信心中等"


def _dividends_by_stock(records: list[DividendRecord]) -> dict[str, list[DividendRecord]]:
    by_stock: dict[str, list[DividendRecord]] = {}
    for record in records:
        by_stock.setdefault(record.stock_id, []).append(record)
    return by_stock


def _dedupe_dividend_records(records: list[DividendRecord]) -> list[DividendRecord]:
    ex_dividend_amounts_by_year: dict[tuple[str, int], list[float]] = {}
    for record in records:
        if record.source == "TWSE_TWT49U":
            ex_dividend_amounts_by_year.setdefault((record.stock_id, record.year), []).append(
                record.cash_dividend
            )

    by_key: dict[tuple[str, int, str], DividendRecord] = {}
    for record in records:
        if record.source == "TWSE_T187AP45":
            paid_amounts = ex_dividend_amounts_by_year.get((record.stock_id, record.year), [])
            if any(abs(record.cash_dividend - paid_amount) < 0.01 for paid_amount in paid_amounts):
                continue
        key = (record.stock_id, record.year, record.period)
        current = by_key.get(key)
        if current is None or current.source == "TWSE_TWT49U":
            by_key[key] = record
    return sorted(by_key.values(), key=lambda item: (item.stock_id, item.year, item.period), reverse=True)


def _annual_cash_dividends_by_year(records: list[DividendRecord]) -> dict[int, float]:
    annual_values: dict[int, float] = {}
    by_year: dict[int, list[DividendRecord]] = {}
    for record in records:
        if record.cash_dividend > 0 or record.stock_dividend > 0:
            by_year.setdefault(record.year, []).append(record)

    for year, year_records in by_year.items():
        ex_dividend_records = [item for item in year_records if item.source == "TWSE_TWT49U"]
        if ex_dividend_records:
            annual_values[year] = sum(item.cash_dividend for item in year_records)
            continue
        annual_records = [item for item in year_records if item.period == "年度"]
        if annual_records:
            annual_values[year] = sum(item.cash_dividend for item in annual_records)
            continue
        quarter_records = [item for item in year_records if "季" in item.period]
        if len(quarter_records) >= 4:
            annual_values[year] = sum(item.cash_dividend for item in quarter_records)
    return annual_values


def _recent_annual_cash_values(
    annual_cash_by_year: dict[int, float],
    historical_years: int,
) -> list[float]:
    if historical_years < 1:
        return []
    return [
        annual_cash_by_year[year]
        for year in sorted(annual_cash_by_year, reverse=True)[:historical_years]
    ]
