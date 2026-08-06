"""TPEx（上櫃）來源 adapter。

設計原則（docs/tpex-評估.md）：
- 與 TWSE 分開維護：TpexClient 獨立類，不塞進 TwseClient 分支；source tag 一律 TPEX_*。
- 日線歷史用 www/afterTrading/tradingStock（月查詢）：欄位為「成交仟股/成交仟元」，
  寫入 DailyPrice 前必須 ×1000——這是最容易污染量價分析的差異，golden test 鎖住。
- OpenAPI 欄位有英文/中文與拼字差異風險：一律走 alias 候選表取值；
  整批解析不出關鍵欄位（代號/收盤）→ 丟 TpexError 讓上層當失敗重試，不靜默寫壞資料。
- 第一版不接：上櫃股利分派歷史、上櫃法人（tpex-評估列為中/中高風險，待 fixture 驗證後二版再接）。

共用解析函式直接取自 app.sync.twse 模組層（民國日期/數字清理/營收/財報 row parser）——
TPEx 的 mopsfin_* 端點欄位與 TWSE t187ap* 相同（中文 key），視為既定契約複用。
"""
from __future__ import annotations

import json
import ssl
import threading
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import date
from decimal import InvalidOperation
from typing import Any

from app.models import DailyPrice, FinancialStatement, MarketValuation, MonthlyRevenue, StockProfile
from app.sync.twse import (  # noqa: F401 - 模組層共用 parser（契約見本檔 docstring）
    _blank_to_none,
    _clean_number,
    _financial_statement_from_rows,
    _iter_month_starts,
    _monthly_revenue_from_row,
    _parse_float,
    _parse_gregorian_date,
    _parse_int,
    _parse_optional_float,
    _parse_optional_int,
    _parse_roc_compact_date,
    _parse_roc_slash_date,
)

FetchJson = Callable[[str], Any]

SOURCE_TRADING_STOCK = "TPEX_TRADING_STOCK"
SOURCE_MAINBOARD_QUOTES = "TPEX_MAINBOARD_QUOTES"


class TpexError(RuntimeError):
    """Raised when a TPEx response cannot be fetched or parsed."""


class TpexClient:
    OPENAPI_BASE = "https://www.tpex.org.tw/openapi/v1"
    TRADING_STOCK_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock"
    THROTTLE_FACTOR_MAX = 32.0
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
        self._throttle_factor = 1.0
        self._fetch_json = fetch_json or self._default_fetch_json
        self._cache_enabled = fetch_json is None
        self._ssl_context = ssl.create_default_context()

    # ---- 上櫃清單 ---------------------------------------------------------
    def fetch_otc_profiles(self) -> list[StockProfile]:
        payload = self._fetch_shared_json(f"{self.OPENAPI_BASE}/mopsfin_t187ap03_O")
        if not isinstance(payload, list):
            raise TpexError("Unexpected TPEx company profile payload.")

        profiles: list[StockProfile] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            stock_id = _pick_text(row, ("SecuritiesCompanyCode", "公司代號", "Code"))
            if not stock_id:
                continue
            name = _pick_text(row, ("CompanyName", "公司名稱", "Name"))
            short_name = (
                _pick_text(
                    row,
                    ("CompanyAbbreviation", "公司簡稱", "AbbreviatedName", "Abbreviation"),
                )
                or name
            )
            profiles.append(
                StockProfile(
                    stock_id=stock_id,
                    name=name,
                    short_name=short_name or name,
                    industry_code=_blank_to_none(
                        _pick(row, ("SecuritiesIndustryCode", "產業別", "IndustryCode"))
                    ),
                    market="TPEX",
                    listed_date=_parse_flexible_day(
                        _pick(row, ("DateOfListing", "上櫃日期", "上市日期", "ListingDate"))
                    ),
                )
            )
        if payload and not profiles:
            raise TpexError("All TPEx profile rows were unparsable (field drift?).")
        return profiles

    def fetch_profile(self, stock_id: str) -> StockProfile | None:
        stock_id = stock_id.strip()
        for profile in self.fetch_otc_profiles():
            if profile.stock_id == stock_id:
                return profile
        return None

    # ---- 日線歷史（月查詢） ----------------------------------------------
    def fetch_daily_prices_for_month(self, stock_id: str, month_start: date) -> list[DailyPrice]:
        query = urllib.parse.urlencode(
            {
                "code": stock_id,
                "date": month_start.strftime("%Y/%m/01"),
                "response": "json",
            }
        )
        payload = self._fetch_json(f"{self.TRADING_STOCK_URL}?{query}")
        if not isinstance(payload, dict):
            raise TpexError("Unexpected TPEx trading-stock payload.")

        stat = str(payload.get("stat", ""))
        if stat and stat.lower() != "ok":
            return []

        rows = _trading_stock_rows(payload)
        prices: list[DailyPrice] = []
        unparsable = 0
        for row in rows:
            if not isinstance(row, list) or len(row) < 9:
                unparsable += 1
                continue
            try:
                prices.append(
                    DailyPrice(
                        stock_id=stock_id,
                        date=_parse_roc_slash_date(row[0]),
                        # 上櫃日線是「成交仟股/成交仟元」，必須 ×1000 轉成股/元。
                        volume=_parse_thousand_units(row[1]),
                        trade_value=_parse_thousand_units(row[2]),
                        open=_parse_float(row[3]),
                        high=_parse_float(row[4]),
                        low=_parse_float(row[5]),
                        close=_parse_float(row[6]),
                        change=_parse_optional_float(row[7]),
                        transaction_count=_parse_int(row[8]),
                        source=SOURCE_TRADING_STOCK,
                    )
                )
            except (TypeError, ValueError, InvalidOperation):
                unparsable += 1
                continue
        if rows and not prices and unparsable:
            raise TpexError(
                f"All {len(rows)} TPEx trading-stock rows unparsable for {stock_id} {month_start:%Y-%m}."
            )
        return prices

    def fetch_daily_prices(
        self,
        stock_id: str,
        start_date: date,
        end_date: date,
        *,
        on_month: Callable[[list[DailyPrice]], None] | None = None,
    ) -> list[DailyPrice]:
        """逐月抓上櫃日線；行為（倒序、重試、warning、on_month 漸進回呼）對齊 TwseClient。"""
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")

        def _emit(month_prices: list[DailyPrice]) -> None:
            if on_month is None or not month_prices:
                return
            in_range = [p for p in month_prices if start_date <= p.date <= end_date]
            if in_range:
                on_month(in_range)

        prices: list[DailyPrice] = []
        self.last_warnings = []
        fetch_order = list(reversed(list(_iter_month_starts(start_date, end_date))))
        failed_months: list[tuple[date, TpexError]] = []
        for index, month_start in enumerate(fetch_order):
            try:
                month_prices = self.fetch_daily_prices_for_month(stock_id, month_start)
                prices.extend(month_prices)
                _emit(month_prices)
            except TpexError as exc:
                failed_months.append((month_start, exc))
            if index < len(fetch_order) - 1:
                self._sleep_between_requests()

        for index, (month_start, first_error) in enumerate(failed_months):
            self._sleep_between_requests(minimum=self.retry_backoff)
            try:
                month_prices = self.fetch_daily_prices_for_month(stock_id, month_start)
                prices.extend(month_prices)
                _emit(month_prices)
            except TpexError as exc:
                self.last_warnings.append(
                    f"Skipped {stock_id} {month_start:%Y-%m} TPEx daily prices after retry: "
                    f"{exc}; first error: {first_error}"
                )
            if index < len(failed_months) - 1:
                self._sleep_between_requests()

        return [
            price
            for price in sorted(prices, key=lambda item: item.date)
            if start_date <= price.date <= end_date
        ]

    # ---- 全市場最新收盤（top-up 用） --------------------------------------
    def fetch_latest_all_prices(self) -> list[DailyPrice]:
        payload = self._fetch_json(f"{self.OPENAPI_BASE}/tpex_mainboard_quotes")
        if not isinstance(payload, list):
            raise TpexError("Unexpected TPEx mainboard quotes payload.")

        prices: list[DailyPrice] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            stock_id = _pick_text(row, ("SecuritiesCompanyCode", "Code", "股票代號", "公司代號"))
            if not stock_id:
                continue
            try:
                day = _parse_roc_compact_date(_pick(row, ("Date", "資料日期")))
                close = _parse_float(_pick(row, ("Close", "收盤", "ClosingPrice", "收盤價")))
                shares = _parse_optional_int(
                    _pick(row, ("TradingShares", "成交股數", "TradeVolume", "成交量"))
                )
                amount = _parse_optional_int(
                    _pick(row, ("TransactionAmount", "成交金額", "TradeValue"))
                )
                shares, amount = _normalize_quote_units(close, shares, amount)
                prices.append(
                    DailyPrice(
                        stock_id=stock_id,
                        date=day,
                        volume=shares or 0,
                        trade_value=amount,
                        open=_parse_float(_pick(row, ("Open", "開盤", "OpeningPrice"))),
                        high=_parse_float(_pick(row, ("High", "最高", "HighestPrice"))),
                        low=_parse_float(_pick(row, ("Low", "最低", "LowestPrice"))),
                        close=close,
                        change=_parse_optional_float(_pick(row, ("Change", "漲跌", "漲跌價差"))),
                        transaction_count=_parse_optional_int(
                            _pick(row, ("TransactionNumber", "成交筆數", "Transaction"))
                        )
                        or 0,
                        source=SOURCE_MAINBOARD_QUOTES,
                    )
                )
            except (TypeError, ValueError, InvalidOperation):
                continue
        if payload and not prices:
            raise TpexError("All TPEx mainboard quote rows were unparsable (field drift?).")
        return prices

    # ---- 全市場加值資料 ---------------------------------------------------
    def fetch_all_market_valuations(self) -> list[MarketValuation]:
        payload = self._fetch_shared_json(f"{self.OPENAPI_BASE}/tpex_mainboard_peratio_analysis")
        if not isinstance(payload, list):
            raise TpexError("Unexpected TPEx peratio payload.")
        out: list[MarketValuation] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            sid = _pick_text(row, ("SecuritiesCompanyCode", "Code", "股票代號", "公司代號"))
            if not sid:
                continue
            try:
                out.append(
                    MarketValuation(
                        stock_id=sid,
                        date=_parse_roc_compact_date(_pick(row, ("Date", "資料日期"))),
                        pe_ratio=_parse_optional_float(
                            _pick(row, ("PriceEarningRatio", "本益比", "PEratio"))
                        ),
                        dividend_yield=_parse_optional_float(
                            _pick(row, ("DividendYield", "殖利率(%)", "殖利率", "YieldRatio"))
                        ),
                        pb_ratio=_parse_optional_float(
                            _pick(row, ("PriceBookRatio", "股價淨值比", "PBratio"))
                        ),
                    )
                )
            except (TypeError, ValueError, InvalidOperation):
                continue
        return out

    def fetch_market_valuation(self, stock_id: str) -> MarketValuation | None:
        stock_id = stock_id.strip()
        for item in self.fetch_all_market_valuations():
            if item.stock_id == stock_id:
                return item
        return None

    def fetch_all_monthly_revenues(self) -> list[MonthlyRevenue]:
        payload = self._fetch_shared_json(f"{self.OPENAPI_BASE}/mopsfin_t187ap05_O")
        if not isinstance(payload, list):
            raise TpexError("Unexpected TPEx monthly revenue payload.")
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

    def fetch_monthly_revenue(self, stock_id: str) -> MonthlyRevenue | None:
        stock_id = stock_id.strip()
        for item in self.fetch_all_monthly_revenues():
            if item.stock_id == stock_id:
                return item
        return None

    def fetch_all_financial_statements(self) -> list[FinancialStatement]:
        income = self._fetch_shared_json(f"{self.OPENAPI_BASE}/mopsfin_t187ap06_O_ci")
        balance = self._fetch_shared_json(f"{self.OPENAPI_BASE}/mopsfin_t187ap07_O_ci")
        if not isinstance(income, list) or not isinstance(balance, list):
            raise TpexError("Unexpected TPEx financial statement payload.")
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

    def fetch_financial_statement(self, stock_id: str) -> FinancialStatement | None:
        stock_id = stock_id.strip()
        for item in self.fetch_all_financial_statements():
            if item.stock_id == stock_id:
                return item
        return None

    # ---- 基礎設施（與 TwseClient 同款：retry / 自適應限流 / 共用快取） ----
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

    def throttle_factor(self) -> float:
        return self._throttle_factor

    def _register_success(self) -> None:
        self._throttle_factor = max(1.0, self._throttle_factor / 2.0)

    def _register_failure(self) -> None:
        self._throttle_factor = min(self.THROTTLE_FACTOR_MAX, self._throttle_factor * 2.0)

    def _sleep_between_requests(self, minimum: float = 0.0) -> None:
        if self.request_interval <= 0:
            return
        time.sleep(max(minimum, self.request_interval * self._throttle_factor))

    def _default_fetch_json(self, url: str) -> Any:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "stock-translator/0.1 (+local-first MVP)",
            },
        )
        last_message = f"Cannot fetch TPEx url: {url}"
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
                    payload = json.loads(raw.decode("utf-8-sig"))
                    self._register_success()
                    return payload
                except json.JSONDecodeError as exc:
                    last_message = f"TPEx returned non-JSON content: {url}"
                    last_error = exc
            except Exception as exc:  # pragma: no cover - exercised by smoke checks
                last_message = f"Cannot fetch TPEx url: {url}"
                last_error = exc
            if attempt < self.max_retries and self.retry_backoff > 0:
                time.sleep(self.retry_backoff * (attempt + 1))
        self._register_failure()
        raise TpexError(last_message) from last_error


# ---- 模組層小工具 ---------------------------------------------------------
def _pick(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """依候選 key 順序取第一個非空值（TPEx OpenAPI 欄位命名有英文/中文差異）。"""
    for key in keys:
        if key in row:
            value = row.get(key)
            if str(value or "").strip() != "":
                return value
    return None


def _pick_text(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    return str(_pick(row, keys) or "").strip()


def _parse_thousand_units(value: Any) -> int:
    """上櫃日線的「成交仟股/成交仟元」→ 股/元（×1000）。"""
    text = _clean_number(value)
    if not text:
        return 0
    return int(round(float(text) * 1000))


def _normalize_quote_units(
    close: float,
    shares: int | None,
    amount: int | None,
) -> tuple[int | None, int | None]:
    """量能單位自校驗：amount/shares（成交均價）應與 close 同量級。

    - ratio ≈ close        → 單位正確（股/元），原樣。
    - ratio ≈ close×1000   → shares 被「仟股」小報了三個量級 → shares×1000。
    - ratio ≈ close/1000   → amount 被「仟元」小報了三個量級 → amount×1000。
    已知限制：兩者「同時」是仟單位時比值正常、檢不出來——fixture 假設此端點
    是股/元（英文 key TradingShares/TransactionAmount 慣例）；欄位漂移由測試鎖住。
    其他異常組合原樣返回（寧可量能存疑，不硬猜放大）。
    """
    if not shares or not amount or close <= 0:
        return shares, amount
    ratio = amount / shares
    if ratio <= 0:
        return shares, amount
    if ratio >= 200 * close:
        return shares * 1000, amount
    if ratio <= close / 200:
        return shares, amount * 1000
    return shares, amount


def _parse_flexible_day(value: Any) -> date | None:
    """上櫃日期欄可能是西元 YYYYMMDD 或民國 7 碼；都試，失敗回 None（有 fallback 行為）。"""
    text = str(value or "").strip()
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    try:
        if len(digits) == 8:
            return _parse_gregorian_date(digits)
        if len(digits) == 7:
            return _parse_roc_compact_date(digits)
    except (TypeError, ValueError):
        return None
    return None


def _trading_stock_rows(payload: dict[str, Any]) -> list[Any]:
    """tradingStock 回傳把資料包在 tables[0].data；防禦性也接受頂層 data。"""
    tables = payload.get("tables")
    if isinstance(tables, list) and tables:
        first = tables[0]
        if isinstance(first, dict) and isinstance(first.get("data"), list):
            return first["data"]
    data = payload.get("data")
    return data if isinstance(data, list) else []
