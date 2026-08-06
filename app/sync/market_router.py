"""市場路由：把「這檔是上市還是上櫃」的判斷收在一個地方。

MarketRoutedClient 對 StockSyncService / bulk_runner 提供與 TwseClient 相同的
單檔方法介面，內部依 market 把呼叫轉給 TwseClient 或 TpexClient：

- market == "TPEX"      → TpexClient
- 其他（含未知/None）   → TwseClient（預設；台股歷史行為不變）
- fetch_profile 未知股  → 先查 TWSE，查無再查 TPEX（新股探測，順便定 market）

TPEx 第一版不支援的資料（股利分派歷史、上櫃法人）回空集合，不丟例外——
消費端本來就有「資料不足」的空態，白話層會說「資料待補」而不是壞掉。
"""
from __future__ import annotations

import inspect
from collections.abc import Callable
from datetime import date
from typing import Any

from app.models import (
    DailyPrice,
    DividendRecord,
    FinancialStatement,
    InstitutionalTrade,
    MarketValuation,
    MonthlyRevenue,
    StockProfile,
)
from app.sync.tpex import TpexClient
from app.sync.twse import TwseClient

MarketLookup = Callable[[str], str | None]


def store_market_lookup(store: Any) -> MarketLookup:
    """由本地 profile 查 market；查不到回 None（路由端當 TWSE 預設）。"""

    def lookup(stock_id: str) -> str | None:
        getter = getattr(store, "get_profile", None)
        if getter is None:
            return None
        try:
            profile = getter(stock_id)
        except Exception:  # noqa: BLE001 - 查不到就走預設路由
            return None
        market = getattr(profile, "market", None) if profile is not None else None
        return str(market).upper() if market else None

    return lookup


class MarketRoutedClient:
    def __init__(
        self,
        twse: TwseClient,
        tpex: TpexClient,
        *,
        market_lookup: MarketLookup,
    ) -> None:
        self.twse = twse
        self.tpex = tpex
        self._market_lookup = market_lookup
        self.last_warnings: list[str] = []

    # ---- 路由核心 ----------------------------------------------------------
    def _is_tpex(self, stock_id: str) -> bool:
        try:
            market = self._market_lookup(stock_id.strip())
        except Exception:  # noqa: BLE001 - lookup 壞掉走預設 TWSE
            return False
        return str(market or "").upper() == "TPEX"

    def _adopt_warnings(self, client: Any) -> None:
        self.last_warnings = list(getattr(client, "last_warnings", []))

    # ---- 日線 --------------------------------------------------------------
    def fetch_daily_prices(
        self,
        stock_id: str,
        start_date: date,
        end_date: date,
        *,
        on_month: Callable[[list[DailyPrice]], None] | None = None,
    ) -> list[DailyPrice]:
        client = self.tpex if self._is_tpex(stock_id) else self.twse
        if on_month is not None and _supports_on_month(client):
            prices = client.fetch_daily_prices(stock_id, start_date, end_date, on_month=on_month)
        else:
            prices = client.fetch_daily_prices(stock_id, start_date, end_date)
            if on_month is not None and prices:
                # 子 client 不支援逐月回呼（測試 stub 等）→ 整批一次回呼，行為等價舊路徑。
                on_month(list(prices))
        self._adopt_warnings(client)
        return prices

    # ---- profile：未知股先 TWSE 再 TPEX 探測 -------------------------------
    def fetch_profile(self, stock_id: str) -> StockProfile | None:
        if self._is_tpex(stock_id):
            profile = self.tpex.fetch_profile(stock_id)
            self._adopt_warnings(self.tpex)
            return profile
        profile = self.twse.fetch_profile(stock_id)
        self._adopt_warnings(self.twse)
        if profile is not None:
            return profile
        try:
            tpex_profile = self.tpex.fetch_profile(stock_id)
        except Exception:  # noqa: BLE001 - 探測失敗不阻斷（維持 TWSE 查無的原行為）
            return None
        return tpex_profile

    # ---- 加值資料 ----------------------------------------------------------
    def fetch_market_valuation(self, stock_id: str) -> MarketValuation | None:
        client = self.tpex if self._is_tpex(stock_id) else self.twse
        value = client.fetch_market_valuation(stock_id)
        self._adopt_warnings(client)
        return value

    def fetch_monthly_revenue(self, stock_id: str) -> MonthlyRevenue | None:
        client = self.tpex if self._is_tpex(stock_id) else self.twse
        value = client.fetch_monthly_revenue(stock_id)
        self._adopt_warnings(client)
        return value

    def fetch_financial_statement(self, stock_id: str) -> FinancialStatement | None:
        client = self.tpex if self._is_tpex(stock_id) else self.twse
        value = client.fetch_financial_statement(stock_id)
        self._adopt_warnings(client)
        return value

    # ---- TPEx 第一版不支援：股利 / 法人（回空，不丟例外） ------------------
    def fetch_dividend_records(self, stock_id: str) -> list[DividendRecord]:
        if self._is_tpex(stock_id):
            self.last_warnings = []
            return []
        records = self.twse.fetch_dividend_records(stock_id)
        self._adopt_warnings(self.twse)
        return records

    def fetch_historical_dividend_records(
        self,
        stock_id: str,
        start_date: date,
        end_date: date,
    ) -> list[DividendRecord]:
        if self._is_tpex(stock_id):
            self.last_warnings = []
            return []
        records = self.twse.fetch_historical_dividend_records(stock_id, start_date, end_date)
        self._adopt_warnings(self.twse)
        return records

    def fetch_institutional_trades(
        self,
        stock_id: str,
        start_date: date,
        end_date: date,
        **kwargs: Any,
    ) -> list[InstitutionalTrade]:
        if self._is_tpex(stock_id):
            self.last_warnings = []
            return []
        trades = self.twse.fetch_institutional_trades(stock_id, start_date, end_date, **kwargs)
        self._adopt_warnings(self.twse)
        return trades

    # ---- bulk extra_status 用 ---------------------------------------------
    def throttle_factor(self) -> float:
        try:
            return max(float(self.twse.throttle_factor()), float(self.tpex.throttle_factor()))
        except Exception:  # noqa: BLE001
            return 1.0


def _supports_on_month(client: Any) -> bool:
    try:
        return "on_month" in inspect.signature(client.fetch_daily_prices).parameters
    except (TypeError, ValueError):
        return False
