from __future__ import annotations

import json
import ssl
import threading
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from app.analyze.twse_calendar import is_twse_trading_day
from app.models import (
    DailyPrice,
    DividendRecord,
    FinancialStatement,
    InstitutionalTrade,
    IntradayQuote,
    MarketValuation,
    MonthlyRevenue,
    StockProfile,
)

FetchJson = Callable[[str], Any]


class TwseError(RuntimeError):
    """Raised when a TWSE response cannot be fetched or parsed."""


class TwseClient:
    OPENAPI_BASE = "https://openapi.twse.com.tw/v1"
    STOCK_DAY_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"
    EX_RIGHT_URL = "https://www.twse.com.tw/rwd/zh/exRight/TWT49U"
    MIS_QUOTE_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
    T86_URL = "https://www.twse.com.tw/rwd/zh/fund/T86"
    _SHARED_CACHE_TTL_SECONDS = 15 * 60
    _shared_payload_cache: dict[str, tuple[float, Any]] = {}
    _shared_payload_cache_lock = threading.Lock()

    def __init__(
        self,
        *,
        timeout: float = 20.0,
        request_interval: float = 0.2,
        max_retries: int = 2,
        retry_backoff: float = 0.6,
        fetch_json: FetchJson | None = None,
    ) -> None:
        self.timeout = timeout
        self.request_interval = request_interval
        self.max_retries = max(0, max_retries)
        self.retry_backoff = max(0.0, retry_backoff)
        self.last_warnings: list[str] = []
        self._fetch_json = fetch_json or self._default_fetch_json
        self._cache_enabled = fetch_json is None
        self._ssl_context = ssl.create_default_context()

    def fetch_listed_profiles(self) -> list[StockProfile]:
        payload = self._fetch_shared_json(f"{self.OPENAPI_BASE}/opendata/t187ap03_L")
        if not isinstance(payload, list):
            raise TwseError("Unexpected TWSE company profile payload.")

        profiles: list[StockProfile] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            stock_id = str(row.get("公司代號", "")).strip()
            if not stock_id:
                continue
            name = str(row.get("公司名稱", "")).strip()
            short_name = str(row.get("公司簡稱", "")).strip() or name
            profiles.append(
                StockProfile(
                    stock_id=stock_id,
                    name=name,
                    short_name=short_name,
                    industry_code=_blank_to_none(row.get("產業別")),
                    market="TWSE",
                    listed_date=_parse_gregorian_date(row.get("上市日期")),
                    source_updated_at=_parse_roc_compact_date(row.get("出表日期")),
                )
            )
        return profiles

    def fetch_profile(self, stock_id: str) -> StockProfile | None:
        stock_id = stock_id.strip()
        for profile in self.fetch_listed_profiles():
            if profile.stock_id == stock_id:
                return profile
        return None

    def fetch_daily_prices(
        self,
        stock_id: str,
        start_date: date,
        end_date: date,
    ) -> list[DailyPrice]:
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")

        prices: list[DailyPrice] = []
        self.last_warnings = []
        months = list(_iter_month_starts(start_date, end_date))
        fetch_order = list(reversed(months))
        failed_months: list[tuple[date, TwseError]] = []
        for index, month_start in enumerate(fetch_order):
            try:
                prices.extend(self.fetch_daily_prices_for_month(stock_id, month_start))
            except TwseError as exc:
                failed_months.append((month_start, exc))
            if index < len(fetch_order) - 1 and self.request_interval > 0:
                time.sleep(self.request_interval)

        for index, (month_start, first_error) in enumerate(failed_months):
            if self.request_interval > 0:
                time.sleep(max(self.request_interval, self.retry_backoff))
            try:
                prices.extend(self.fetch_daily_prices_for_month(stock_id, month_start))
            except TwseError as exc:
                self.last_warnings.append(
                    f"Skipped {stock_id} {month_start:%Y-%m} daily prices after retry: "
                    f"{exc}; first error: {first_error}"
                )
            if index < len(failed_months) - 1 and self.request_interval > 0:
                time.sleep(self.request_interval)

        return [
            price
            for price in sorted(prices, key=lambda item: item.date)
            if start_date <= price.date <= end_date
        ]

    def fetch_daily_prices_for_month(
        self,
        stock_id: str,
        month_start: date,
    ) -> list[DailyPrice]:
        query = urllib.parse.urlencode(
            {
                "date": month_start.strftime("%Y%m01"),
                "stockNo": stock_id,
                "response": "json",
            }
        )
        payload = self._fetch_json(f"{self.STOCK_DAY_URL}?{query}")
        if not isinstance(payload, dict):
            raise TwseError("Unexpected TWSE stock day payload.")

        stat = str(payload.get("stat", ""))
        if stat and stat.upper() != "OK":
            return []

        rows = payload.get("data", [])
        if not isinstance(rows, list):
            raise TwseError("Unexpected TWSE stock day rows.")

        prices: list[DailyPrice] = []
        unparsable = 0
        for row in rows:
            if not isinstance(row, list) or len(row) < 9:
                unparsable += 1
                continue
            note = str(row[9]).strip() if len(row) > 9 else ""
            change_marker = _change_marker(row[7])
            if change_marker:
                note = f"{note}; {change_marker}" if note else change_marker
            try:
                prices.append(
                    DailyPrice(
                        stock_id=stock_id,
                        date=_parse_roc_slash_date(row[0]),
                        volume=_parse_int(row[1]),
                        trade_value=_parse_int(row[2]),
                        open=_parse_float(row[3]),
                        high=_parse_float(row[4]),
                        low=_parse_float(row[5]),
                        close=_parse_float(row[6]),
                        change=_parse_optional_float(row[7]),
                        transaction_count=_parse_int(row[8]),
                        note=note,
                        source="TWSE_STOCK_DAY",
                    )
                )
            except (TypeError, ValueError, InvalidOperation):
                # 單一列(某天的特殊值)解析失敗 → 只跳過該列，不要連累整個月被丟掉。
                unparsable += 1
                continue
        if rows and not prices and unparsable:
            # 有資料列卻一筆都解析不出來 → 可能是格式變動，讓上層當失敗（會重試 / 記 warning）。
            raise TwseError(
                f"All {len(rows)} TWSE stock-day rows unparsable for {stock_id} {month_start:%Y-%m}."
            )
        return prices

    def fetch_latest_all_prices(self) -> list[DailyPrice]:
        payload = self._fetch_json(f"{self.OPENAPI_BASE}/exchangeReport/STOCK_DAY_ALL")
        if not isinstance(payload, list):
            raise TwseError("Unexpected TWSE latest daily payload.")

        prices: list[DailyPrice] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            stock_id = str(row.get("Code", "")).strip()
            if not stock_id:
                continue
            try:
                prices.append(
                    DailyPrice(
                        stock_id=stock_id,
                        date=_parse_roc_compact_date(row.get("Date")),
                        volume=_parse_int(row.get("TradeVolume")),
                        trade_value=_parse_int(row.get("TradeValue")),
                        open=_parse_float(row.get("OpeningPrice")),
                        high=_parse_float(row.get("HighestPrice")),
                        low=_parse_float(row.get("LowestPrice")),
                        close=_parse_float(row.get("ClosingPrice")),
                        change=_parse_optional_float(row.get("Change")),
                        transaction_count=_parse_int(row.get("Transaction")),
                        source="TWSE_STOCK_DAY_ALL",
                    )
                )
            except (TypeError, ValueError, InvalidOperation):
                continue
        return prices

    def fetch_dividend_records(self, stock_id: str) -> list[DividendRecord]:
        payload = self._fetch_shared_json(f"{self.OPENAPI_BASE}/opendata/t187ap45_L")
        if not isinstance(payload, list):
            raise TwseError("Unexpected TWSE dividend payload.")

        records: list[DividendRecord] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            if str(row.get("公司代號", "")).strip() != stock_id:
                continue
            records.append(_dividend_record_from_row(stock_id, row))
        return sorted(records, key=lambda item: (item.year, item.period), reverse=True)

    def fetch_all_dividend_records(self) -> list[DividendRecord]:
        payload = self._fetch_shared_json(f"{self.OPENAPI_BASE}/opendata/t187ap45_L")
        if not isinstance(payload, list):
            raise TwseError("Unexpected TWSE dividend payload.")

        records: list[DividendRecord] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            stock_id = str(row.get("公司代號", "")).strip()
            if not stock_id:
                continue
            try:
                records.append(_dividend_record_from_row(stock_id, row))
            except (TypeError, ValueError, InvalidOperation):
                continue
        return sorted(records, key=lambda item: (item.stock_id, item.year, item.period), reverse=True)

    def fetch_historical_dividend_records(
        self,
        stock_id: str,
        start_date: date,
        end_date: date,
    ) -> list[DividendRecord]:
        records: list[DividendRecord] = []
        years = list(range(start_date.year, end_date.year + 1))
        for index, year in enumerate(years):
            query = urllib.parse.urlencode(
                {
                    "startDate": f"{year}0101",
                    "endDate": f"{year}1231",
                    "response": "json",
                }
            )
            try:
                payload = self._fetch_shared_json(f"{self.EX_RIGHT_URL}?{query}")
            except TwseError as exc:
                self.last_warnings.append(
                    f"Skipped {stock_id} {year} dividend history: {exc}"
                )
                continue
            if not isinstance(payload, dict):
                raise TwseError("Unexpected TWSE ex-right payload.")
            stat = str(payload.get("stat", ""))
            if stat and stat.upper() != "OK":
                continue
            rows = payload.get("data", [])
            if not isinstance(rows, list):
                raise TwseError("Unexpected TWSE ex-right rows.")
            for row in rows:
                if not isinstance(row, list) or len(row) < 7:
                    continue
                if str(row[1]).strip() != stock_id:
                    continue
                ex_right_type = str(row[6]).strip()
                if ex_right_type != "息":
                    continue
                ex_date = _parse_roc_chinese_date(row[0])
                if not start_date <= ex_date <= end_date:
                    continue
                cash_dividend = _parse_optional_float(row[5]) or 0.0
                if cash_dividend <= 0:
                    continue
                records.append(
                    DividendRecord(
                        stock_id=stock_id,
                        year=ex_date.year - 1911,
                        period=f"除息 {ex_date:%m/%d}",
                        status="除息",
                        board_date=ex_date,
                        shareholder_meeting_date=None,
                        cash_dividend=cash_dividend,
                        stock_dividend=0.0,
                        source_updated_at=None,
                        note="TWSE 除權息計算結果；僅使用息值作現金股利，權值不是每股股票股利。",
                        source="TWSE_TWT49U",
                    )
                )
            if index < len(years) - 1 and self.request_interval > 0:
                time.sleep(self.request_interval)

        return sorted(records, key=lambda item: (item.year, item.board_date or date.min), reverse=True)

    def fetch_all_historical_dividend_records(
        self,
        start_date: date,
        end_date: date,
    ) -> list[DividendRecord]:
        records: list[DividendRecord] = []
        self.last_warnings = []
        years = list(range(start_date.year, end_date.year + 1))
        for index, year in enumerate(years):
            query = urllib.parse.urlencode(
                {
                    "startDate": f"{year}0101",
                    "endDate": f"{year}1231",
                    "response": "json",
                }
            )
            try:
                payload = self._fetch_shared_json(f"{self.EX_RIGHT_URL}?{query}")
            except TwseError as exc:
                self.last_warnings.append(f"Skipped {year} dividend history: {exc}")
                continue
            if not isinstance(payload, dict):
                raise TwseError("Unexpected TWSE ex-right payload.")
            stat = str(payload.get("stat", ""))
            if stat and stat.upper() != "OK":
                continue
            rows = payload.get("data", [])
            if not isinstance(rows, list):
                raise TwseError("Unexpected TWSE ex-right rows.")
            for row in rows:
                if not isinstance(row, list) or len(row) < 7:
                    continue
                stock_id = str(row[1]).strip()
                if not stock_id:
                    continue
                ex_right_type = str(row[6]).strip()
                if ex_right_type != "息":
                    continue
                try:
                    ex_date = _parse_roc_chinese_date(row[0])
                    cash_dividend = _parse_optional_float(row[5]) or 0.0
                except (TypeError, ValueError, InvalidOperation):
                    continue
                if not start_date <= ex_date <= end_date or cash_dividend <= 0:
                    continue
                records.append(
                    DividendRecord(
                        stock_id=stock_id,
                        year=ex_date.year - 1911,
                        period=f"除息 {ex_date:%m/%d}",
                        status="除息",
                        board_date=ex_date,
                        shareholder_meeting_date=None,
                        cash_dividend=cash_dividend,
                        stock_dividend=0.0,
                        source_updated_at=None,
                        note="TWSE 除權息計算結果；僅使用息值作現金股利，權值不是每股股票股利。",
                        source="TWSE_TWT49U",
                    )
                )
            if index < len(years) - 1 and self.request_interval > 0:
                time.sleep(self.request_interval)

        return sorted(records, key=lambda item: (item.stock_id, item.year, item.board_date or date.min), reverse=True)

    def fetch_market_valuation(self, stock_id: str) -> MarketValuation | None:
        payload = self._fetch_shared_json(f"{self.OPENAPI_BASE}/exchangeReport/BWIBBU_ALL")
        if not isinstance(payload, list):
            raise TwseError("Unexpected TWSE valuation payload.")

        for row in payload:
            if not isinstance(row, dict):
                continue
            if str(row.get("Code", "")).strip() == stock_id:
                return MarketValuation(
                    stock_id=stock_id,
                    date=_parse_roc_compact_date(row.get("Date")),
                    pe_ratio=_parse_optional_float(row.get("PEratio")),
                    dividend_yield=_parse_optional_float(row.get("DividendYield")),
                    pb_ratio=_parse_optional_float(row.get("PBratio")),
                )
        return None

    def fetch_monthly_revenue(self, stock_id: str) -> MonthlyRevenue | None:
        payload = self._fetch_shared_json(f"{self.OPENAPI_BASE}/opendata/t187ap05_L")
        if not isinstance(payload, list):
            raise TwseError("Unexpected TWSE monthly revenue payload.")

        for row in payload:
            if not isinstance(row, dict):
                continue
            if str(row.get("公司代號", "")).strip() == stock_id:
                return _monthly_revenue_from_row(stock_id, row)
        return None

    def fetch_financial_statement(self, stock_id: str) -> FinancialStatement | None:
        income_payload = self._fetch_shared_json(f"{self.OPENAPI_BASE}/opendata/t187ap06_L_ci")
        balance_payload = self._fetch_shared_json(f"{self.OPENAPI_BASE}/opendata/t187ap07_L_ci")
        if not isinstance(income_payload, list) or not isinstance(balance_payload, list):
            raise TwseError("Unexpected TWSE financial statement payload.")

        income_row = _find_company_row(income_payload, stock_id)
        balance_row = _find_company_row(balance_payload, stock_id)
        if income_row is None and balance_row is None:
            return None
        return _financial_statement_from_rows(stock_id, income_row, balance_row)

    def fetch_institutional_trade_for_stock_on(
        self,
        stock_id: str,
        day: date,
    ) -> InstitutionalTrade | None:
        """抓某一交易日 T86 三大法人買賣超，取出指定個股那一列。非交易日/未公布回 None。"""
        query = urllib.parse.urlencode(
            {
                "date": day.strftime("%Y%m%d"),
                "selectType": "ALLBUT0999",
                "response": "json",
            }
        )
        payload = self._fetch_json(f"{self.T86_URL}?{query}")
        if not isinstance(payload, dict):
            raise TwseError("Unexpected TWSE T86 payload.")
        stat = str(payload.get("stat", ""))
        if stat and stat.upper() != "OK":
            return None
        rows = payload.get("data")
        if not isinstance(rows, list):
            return None
        for row in rows:
            if not isinstance(row, list) or len(row) <= 18:
                continue
            if str(row[0]).strip() != stock_id:
                continue
            try:
                return InstitutionalTrade(
                    stock_id=stock_id,
                    date=day,
                    foreign_net=_parse_int(row[4]),
                    trust_net=_parse_int(row[10]),
                    dealer_net=_parse_int(row[11]),
                    total_net=_parse_int(row[18]),
                )
            except (TypeError, ValueError, InvalidOperation) as exc:
                raise TwseError(f"Cannot parse TWSE T86 row: {row!r}") from exc
        return None

    def fetch_institutional_trades(
        self,
        stock_id: str,
        start_date: date,
        end_date: date,
        *,
        max_days: int = 20,
        skip_dates: set[str] | None = None,
    ) -> list[InstitutionalTrade]:
        """由近往遠逐日抓 T86，收集個股近 max_days 個交易日的三大法人買賣超。

        以『按日』查詢（T86 只能按日），只查台股交易日；遇連續多個交易日無資料即提前停止，
        避免長假或資料缺口時無止盡查詢。任何單日失敗只記 warning，不中斷整體。
        """
        stock_id = stock_id.strip()
        self.last_warnings = []
        results: list[InstitutionalTrade] = []
        day = end_date
        consecutive_empty = 0
        first_attempt = True
        skip_dates = skip_dates or set()
        empty_gate = max(10, min(max_days, 20))
        while day >= start_date and len(results) < max_days:
            trading_day = is_twse_trading_day(day)
            if trading_day and day.isoformat() in skip_dates:
                day -= timedelta(days=1)
                continue
            if trading_day:
                try:
                    trade = self.fetch_institutional_trade_for_stock_on(stock_id, day)
                except TwseError as exc:
                    if first_attempt:
                        # 第一次就連不上（多半是沒網路），直接放棄，別卡住同步
                        raise
                    self.last_warnings.append(
                        f"Skipped {stock_id} {day:%Y-%m-%d} institutional trades: {exc}"
                    )
                    trade = None
                first_attempt = False
                if trade is not None:
                    results.append(trade)
                    consecutive_empty = 0
                else:
                    consecutive_empty += 1
                if self.request_interval > 0:
                    time.sleep(self.request_interval)
                if consecutive_empty >= empty_gate:
                    break
            day -= timedelta(days=1)
        return sorted(results, key=lambda item: item.date)

    def fetch_all_monthly_revenues(self) -> list[MonthlyRevenue]:
        payload = self._fetch_shared_json(f"{self.OPENAPI_BASE}/opendata/t187ap05_L")
        if not isinstance(payload, list):
            raise TwseError("Unexpected TWSE monthly revenue payload.")
        out: list[MonthlyRevenue] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            sid = str(row.get("公司代號", "")).strip()
            if not sid:
                continue
            try:
                out.append(_monthly_revenue_from_row(sid, row))
            except (TypeError, ValueError, InvalidOperation):
                continue
        return out

    def fetch_all_market_valuations(self) -> list[MarketValuation]:
        payload = self._fetch_shared_json(f"{self.OPENAPI_BASE}/exchangeReport/BWIBBU_ALL")
        if not isinstance(payload, list):
            raise TwseError("Unexpected TWSE valuation payload.")
        out: list[MarketValuation] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            sid = str(row.get("Code", "")).strip()
            if not sid:
                continue
            try:
                out.append(
                    MarketValuation(
                        stock_id=sid,
                        date=_parse_roc_compact_date(row.get("Date")),
                        pe_ratio=_parse_optional_float(row.get("PEratio")),
                        dividend_yield=_parse_optional_float(row.get("DividendYield")),
                        pb_ratio=_parse_optional_float(row.get("PBratio")),
                    )
                )
            except (TypeError, ValueError, InvalidOperation):
                continue
        return out

    def fetch_all_financial_statements(self) -> list[FinancialStatement]:
        income = self._fetch_shared_json(f"{self.OPENAPI_BASE}/opendata/t187ap06_L_ci")
        balance = self._fetch_shared_json(f"{self.OPENAPI_BASE}/opendata/t187ap07_L_ci")
        if not isinstance(income, list) or not isinstance(balance, list):
            raise TwseError("Unexpected TWSE financial statement payload.")
        imap = {str(r.get("公司代號", "")).strip(): r for r in income if isinstance(r, dict)}
        bmap = {str(r.get("公司代號", "")).strip(): r for r in balance if isinstance(r, dict)}
        out: list[FinancialStatement] = []
        for sid in set(imap) | set(bmap):
            if not sid:
                continue
            try:
                out.append(_financial_statement_from_rows(sid, imap.get(sid), bmap.get(sid)))
            except (TypeError, ValueError, InvalidOperation):
                continue
        return out

    def fetch_institutional_trades_for_date(self, day: date) -> list[InstitutionalTrade]:
        """某交易日 T86 全市場三大法人買賣超（一次回傳所有個股）。"""
        query = urllib.parse.urlencode(
            {"date": day.strftime("%Y%m%d"), "selectType": "ALLBUT0999", "response": "json"}
        )
        payload = self._fetch_json(f"{self.T86_URL}?{query}")
        if not isinstance(payload, dict):
            raise TwseError("Unexpected TWSE T86 payload.")
        stat = str(payload.get("stat", ""))
        if stat and stat.upper() != "OK":
            return []
        rows = payload.get("data")
        if not isinstance(rows, list):
            return []
        out: list[InstitutionalTrade] = []
        for row in rows:
            if not isinstance(row, list) or len(row) <= 18:
                continue
            sid = str(row[0]).strip()
            if not sid:
                continue
            try:
                out.append(
                    InstitutionalTrade(
                        stock_id=sid,
                        date=day,
                        foreign_net=_parse_int(row[4]),
                        trust_net=_parse_int(row[10]),
                        dealer_net=_parse_int(row[11]),
                        total_net=_parse_int(row[18]),
                    )
                )
            except (TypeError, ValueError, InvalidOperation):
                continue
        return out

    def fetch_intraday_quote(self, stock_id: str) -> IntradayQuote | None:
        query = urllib.parse.urlencode(
            {
                "ex_ch": f"tse_{stock_id}.tw",
                "json": "1",
                "delay": "0",
                "_": int(time.time() * 1000),
            }
        )
        payload = self._fetch_json(f"{self.MIS_QUOTE_URL}?{query}")
        if not isinstance(payload, dict):
            raise TwseError("Unexpected TWSE MIS quote payload.")

        if str(payload.get("rtcode", "")) not in {"0000", ""}:
            raise TwseError(str(payload.get("rtmessage") or "TWSE MIS quote failed."))

        rows = payload.get("msgArray")
        if not isinstance(rows, list) or not rows:
            return None

        row = rows[0]
        if not isinstance(row, dict):
            return None

        quote_stock_id = str(row.get("c") or stock_id).strip()
        ask_prices = _parse_price_levels(row.get("a"))
        bid_prices = _parse_price_levels(row.get("b"))
        return IntradayQuote(
            stock_id=quote_stock_id,
            name=str(row.get("n") or "").strip(),
            full_name=str(row.get("nf") or "").strip(),
            trade_datetime=_parse_mis_datetime(row.get("d"), row.get("t") or row.get("%")),
            current_price=_parse_optional_float(row.get("z"))
            or _parse_optional_float(row.get("pz")),
            previous_close=_parse_optional_float(row.get("y")),
            open_price=_parse_optional_float(row.get("o")),
            high_price=_parse_optional_float(row.get("h")),
            low_price=_parse_optional_float(row.get("l")),
            volume=_parse_optional_int(row.get("v")),
            best_bid_price=bid_prices[0] if bid_prices else None,
            best_ask_price=ask_prices[0] if ask_prices else None,
            bid_prices=bid_prices,
            ask_prices=ask_prices,
            source_delay_ms=_parse_optional_int(payload.get("userDelay")),
        )

    @classmethod
    def clear_shared_cache(cls) -> None:
        with cls._shared_payload_cache_lock:
            cls._shared_payload_cache.clear()

    def _fetch_shared_json(self, url: str) -> Any:
        if not self._cache_enabled:
            return self._fetch_json(url)
        now = time.monotonic()
        with self._shared_payload_cache_lock:
            cached = self._shared_payload_cache.get(url)
            if cached is not None:
                cached_at, payload = cached
                if now - cached_at <= self._SHARED_CACHE_TTL_SECONDS:
                    return payload

        payload = self._fetch_json(url)
        with self._shared_payload_cache_lock:
            self._shared_payload_cache[url] = (now, payload)
        return payload

    def _default_fetch_json(self, url: str) -> Any:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "stock-translator/0.1 (+local-first MVP)",
            },
        )
        last_message = f"Cannot fetch TWSE url: {url}"
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(
                    request,
                    timeout=self.timeout,
                    context=self._ssl_context,
                ) as response:
                    raw = response.read()
                try:
                    return json.loads(raw.decode("utf-8-sig"))
                except json.JSONDecodeError as exc:
                    last_message = f"TWSE returned non-JSON content: {url}"
                    last_error = exc
            except Exception as exc:  # pragma: no cover - exercised by smoke checks
                last_message = f"Cannot fetch TWSE url: {url}"
                last_error = exc

            if attempt < self.max_retries and self.retry_backoff > 0:
                time.sleep(self.retry_backoff * (attempt + 1))

        raise TwseError(last_message) from last_error


def _iter_month_starts(start_date: date, end_date: date) -> Iterable[date]:
    year = start_date.year
    month = start_date.month
    while (year, month) <= (end_date.year, end_date.month):
        yield date(year, month, 1)
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1


def _parse_roc_slash_date(value: Any) -> date:
    year_text, month_text, day_text = str(value).strip().split("/")
    return date(int(year_text) + 1911, int(month_text), int(day_text))


def _parse_roc_chinese_date(value: Any) -> date:
    text = str(value).strip()
    year_text, rest = text.split("年", 1)
    month_text, rest = rest.split("月", 1)
    day_text = rest.removesuffix("日")
    return date(int(year_text) + 1911, int(month_text), int(day_text))


def _parse_roc_compact_date(value: Any) -> date:
    text = str(value).strip()
    if len(text) != 7:
        raise ValueError(f"Expected ROC compact date, got {text!r}")
    return date(int(text[:3]) + 1911, int(text[3:5]), int(text[5:7]))


def _parse_gregorian_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    return date(int(text[:4]), int(text[4:6]), int(text[6:8]))


def _parse_roc_year_month(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) != 5:
        raise ValueError(f"Expected ROC year-month, got {text!r}")
    return f"{int(text[:3]) + 1911:04d}-{int(text[3:5]):02d}"


def _parse_mis_datetime(date_value: Any, time_value: Any) -> datetime | None:
    date_text = str(date_value or "").strip()
    time_text = str(time_value or "").strip()
    if len(date_text) != 8 or not time_text:
        return None
    try:
        return datetime.strptime(f"{date_text} {time_text}", "%Y%m%d %H:%M:%S")
    except ValueError:
        return None


def _parse_optional_roc_compact_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    return _parse_roc_compact_date(text)


def _parse_int(value: Any) -> int:
    text = _clean_number(value)
    if not text:
        return 0
    return int(Decimal(text))


def _parse_optional_int(value: Any) -> int | None:
    text = _clean_number(value)
    if not text:
        return None
    return int(Decimal(text))


def _parse_float(value: Any) -> float:
    text = _clean_number(value)
    if not text:
        raise ValueError("missing numeric value")
    return float(Decimal(text))


def _parse_optional_float(value: Any) -> float | None:
    text = _clean_number(value)
    if not text:
        return None
    return float(Decimal(text))


def _clean_number(value: Any) -> str:
    text = str(value or "").strip().replace(",", "")
    if text in {"", "-", "--", "---", "除權息"}:
        return ""
    while text and text[0] not in "+-.0123456789":
        text = text[1:]
    if text.startswith("+"):
        text = text[1:]
    return text


def _parse_price_levels(value: Any) -> tuple[float, ...]:
    levels: list[float] = []
    for part in str(value or "").split("_"):
        parsed = _parse_optional_float(part)
        if parsed is not None:
            levels.append(parsed)
    return tuple(levels)


def _change_marker(value: Any) -> str | None:
    text = str(value or "").strip()
    if text and text[0] not in "+-.0123456789":
        return f"change_marker={text[0]}"
    return None


def _blank_to_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _find_company_row(payload: list[Any], stock_id: str) -> dict[str, Any] | None:
    for row in payload:
        if isinstance(row, dict) and str(row.get("公司代號", "")).strip() == stock_id:
            return row
    return None


def _dividend_record_from_row(stock_id: str, row: dict[str, Any]) -> DividendRecord:
    earnings_cash = (
        _parse_optional_float(row.get("股東配發-盈餘分配之現金股利(元/股)")) or 0.0
    )
    legal_reserve_cash = (
        _parse_optional_float(row.get("股東配發-法定盈餘公積發放之現金(元/股)")) or 0.0
    )
    capital_reserve_cash = (
        _parse_optional_float(row.get("股東配發-資本公積發放之現金(元/股)")) or 0.0
    )
    cash_dividend = earnings_cash + legal_reserve_cash + capital_reserve_cash
    earnings_stock = (
        _parse_optional_float(row.get("股東配發-盈餘轉增資配股(元/股)")) or 0.0
    )
    legal_reserve_stock = (
        _parse_optional_float(row.get("股東配發-法定盈餘公積轉增資配股(元/股)")) or 0.0
    )
    capital_reserve_stock = (
        _parse_optional_float(row.get("股東配發-資本公積轉增資配股(元/股)")) or 0.0
    )
    stock_dividend = earnings_stock + legal_reserve_stock + capital_reserve_stock
    period = str(row.get("股利所屬年(季)度", "")).strip()
    declared_year = int(str(row.get("股利年度", "0")).strip())
    board_date = _parse_optional_roc_compact_date(row.get("董事會（擬議）股利分派日"))
    distribution_year = declared_year
    if board_date and board_date.year - 1911 > declared_year:
        distribution_year = board_date.year - 1911
    raw_note = str(row.get("備註", "")).strip()
    component_notes = [
        _cash_distribution_component_note(earnings_cash, legal_reserve_cash, capital_reserve_cash),
        _stock_distribution_component_note(earnings_stock, legal_reserve_stock, capital_reserve_stock),
    ]
    if any(component_notes) and raw_note in {"無", "無。"}:
        raw_note = ""

    return DividendRecord(
        stock_id=stock_id,
        year=distribution_year,
        period=period,
        status=str(row.get("決議（擬議）進度", "")).strip(),
        board_date=board_date,
        shareholder_meeting_date=_parse_optional_roc_compact_date(row.get("股東會日期")),
        cash_dividend=cash_dividend,
        stock_dividend=stock_dividend,
        source_updated_at=_parse_optional_roc_compact_date(row.get("出表日期")),
        note=_join_notes(raw_note, *component_notes),
    )


def _cash_distribution_component_note(
    earnings_cash: float, legal_reserve_cash: float, capital_reserve_cash: float
) -> str:
    if legal_reserve_cash <= 0 and capital_reserve_cash <= 0:
        return ""
    return _distribution_component_note(
        "現金股利口徑",
        (
            ("盈餘分配現金", earnings_cash),
            ("法定盈餘公積現金", legal_reserve_cash),
            ("資本公積現金", capital_reserve_cash),
        ),
    )


def _stock_distribution_component_note(
    earnings_stock: float, legal_reserve_stock: float, capital_reserve_stock: float
) -> str:
    if legal_reserve_stock <= 0 and capital_reserve_stock <= 0:
        return ""
    return _distribution_component_note(
        "股票股利口徑",
        (
            ("盈餘轉增資", earnings_stock),
            ("法定盈餘公積轉增資", legal_reserve_stock),
            ("資本公積轉增資", capital_reserve_stock),
        ),
    )


def _distribution_component_note(title: str, components: tuple[tuple[str, float], ...]) -> str:
    parts = [
        f"{label} {_format_per_share_amount(value)}"
        for label, value in components
        if value > 0
    ]
    if not parts:
        return ""
    return f"{title}：含{'、'.join(parts)} 元/股。"


def _format_per_share_amount(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _join_notes(*notes: str) -> str:
    return " ".join(note for note in notes if note)


def _monthly_revenue_from_row(stock_id: str, row: dict[str, Any]) -> MonthlyRevenue:
    return MonthlyRevenue(
        stock_id=stock_id,
        year_month=_parse_roc_year_month(row.get("資料年月")),
        company_name=str(row.get("公司名稱", "")).strip(),
        industry=str(row.get("產業別", "")).strip(),
        current_month_revenue=_parse_int(row.get("營業收入-當月營收")),
        previous_month_revenue=_parse_optional_int(row.get("營業收入-上月營收")),
        last_year_month_revenue=_parse_optional_int(row.get("營業收入-去年當月營收")),
        mom_percent=_parse_optional_float(row.get("營業收入-上月比較增減(%)")),
        yoy_percent=_parse_optional_float(row.get("營業收入-去年同月增減(%)")),
        cumulative_revenue=_parse_optional_int(row.get("累計營業收入-當月累計營收")),
        cumulative_last_year_revenue=_parse_optional_int(row.get("累計營業收入-去年累計營收")),
        cumulative_yoy_percent=_parse_optional_float(row.get("累計營業收入-前期比較增減(%)")),
        source_updated_at=_parse_optional_roc_compact_date(row.get("出表日期")),
        note="" if str(row.get("備註", "")).strip() == "-" else str(row.get("備註", "")).strip(),
    )


def _financial_statement_from_rows(
    stock_id: str,
    income_row: dict[str, Any] | None,
    balance_row: dict[str, Any] | None,
) -> FinancialStatement:
    source_row = income_row or balance_row or {}
    return FinancialStatement(
        stock_id=stock_id,
        year=int(str(source_row.get("年度", "0")).strip()) + 1911,
        quarter=int(str(source_row.get("季別", "0")).strip()),
        company_name=str(source_row.get("公司名稱", "")).strip(),
        revenue=_parse_optional_int((income_row or {}).get("營業收入")),
        gross_profit=_parse_optional_int((income_row or {}).get("營業毛利（毛損）")),
        operating_income=_parse_optional_int((income_row or {}).get("營業利益（損失）")),
        non_operating_income_expense=_parse_optional_int((income_row or {}).get("營業外收入及支出")),
        pre_tax_income=_parse_optional_int((income_row or {}).get("稅前淨利（淨損）")),
        net_income=_parse_optional_int((income_row or {}).get("本期淨利（淨損）")),
        parent_net_income=_parse_optional_int((income_row or {}).get("淨利（淨損）歸屬於母公司業主")),
        eps=_parse_optional_float((income_row or {}).get("基本每股盈餘（元）")),
        total_assets=_parse_optional_int((balance_row or {}).get("資產總額")),
        total_liabilities=_parse_optional_int((balance_row or {}).get("負債總額")),
        parent_equity=_parse_optional_int((balance_row or {}).get("歸屬於母公司業主之權益合計")),
        total_equity=_parse_optional_int((balance_row or {}).get("權益總額")),
        book_value_per_share=_parse_optional_float((balance_row or {}).get("每股參考淨值")),
        source_updated_at=_parse_optional_roc_compact_date(source_row.get("出表日期")),
    )
