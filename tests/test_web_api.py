from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.models import (
    DailyPrice,
    DividendRecord,
    FinancialStatement,
    IntradayQuote,
    MarketValuation,
    MonthlyRevenue,
    StockProfile,
)
from app.analyze.suitability import ValuationSuitability
from app.news.classifier import contains_forbidden
from app.store.sqlite_store import SQLiteStore
from app.glossary.service import glossary_payload
from app.portfolio.models import PortfolioTransaction
from app.web.api import (
    LOCAL_DATA_CACHE_KEY,
    build_cached_local_data_payload,
    build_portfolio_payload,
    build_search_payload,
    build_stock_payload,
    build_watchlist_payload,
    stock_brief_to_json,
)


class WebApiPayloadTests(unittest.TestCase):
    def test_build_stock_payload_contains_profile_prices_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                store.upsert_profiles(
                    [
                        StockProfile(
                            stock_id="2330",
                            name="台灣積體電路製造股份有限公司",
                            short_name="台積電",
                        )
                    ]
                )
                store.upsert_daily_prices(
                    [
                        DailyPrice(
                            stock_id="2330",
                            date=date(2026, 6, 10),
                            open=100,
                            high=105,
                            low=99,
                            close=102,
                            volume=10,
                        ),
                        DailyPrice(
                            stock_id="2330",
                            date=date(2026, 6, 11),
                            open=102,
                            high=108,
                            low=101,
                            close=107,
                            volume=12,
                        ),
                    ]
                )
                store.upsert_dividend_records(
                    [
                        DividendRecord(
                            stock_id="2330",
                            year=115,
                            period="第1季",
                            status="董事會決議",
                            board_date=date(2026, 5, 12),
                            shareholder_meeting_date=None,
                            cash_dividend=7.0,
                            stock_dividend=0.0,
                        )
                    ]
                )
                store.upsert_market_valuations(
                    [
                        MarketValuation(
                            stock_id="2330",
                            date=date(2026, 6, 11),
                            pe_ratio=30.25,
                            dividend_yield=0.98,
                            pb_ratio=9.9,
                        )
                    ]
                )
                store.upsert_monthly_revenues(
                    [
                        MonthlyRevenue(
                            stock_id="2330",
                            year_month="2026-05",
                            company_name="台積電",
                            industry="半導體業",
                            current_month_revenue=416975163,
                            previous_month_revenue=410725118,
                            last_year_month_revenue=320515951,
                            mom_percent=1.52,
                            yoy_percent=30.09,
                            cumulative_revenue=1961803721,
                            cumulative_last_year_revenue=1509336555,
                            cumulative_yoy_percent=29.98,
                            source_updated_at=date(2026, 6, 11),
                        )
                    ]
                )
                store.upsert_financial_statements(
                    [
                        FinancialStatement(
                            stock_id="2330",
                            year=2026,
                            quarter=1,
                            company_name="台積電",
                            revenue=1134103440,
                            gross_profit=751295421,
                            operating_income=658966142,
                            non_operating_income_expense=28833545,
                            pre_tax_income=687799687,
                            net_income=572801304,
                            parent_net_income=572479752,
                            eps=22.08,
                            total_assets=8660949685,
                            total_liabilities=2728560764,
                            parent_equity=5890960252,
                            total_equity=5932388921,
                            book_value_per_share=227.17,
                            source_updated_at=date(2026, 6, 12),
                        )
                    ]
                )
                store.add_to_watchlist("2330")
                store.add_portfolio_transaction(
                    PortfolioTransaction(
                        stock_id="2330",
                        trade_date=date(2026, 6, 1),
                        side="buy",
                        shares=1000,
                        price=100,
                        fee=10,
                        note="測試買進",
                    )
                )

                payload = build_stock_payload(
                    store,
                    "2330",
                    days=3650,
                    quote_provider=FakeQuoteProvider(),
                )
                portfolio_payload = build_portfolio_payload(store)
                search_payload = build_search_payload(store, "台積")
                watchlist_payload = build_watchlist_payload(store)

        self.assertEqual(payload["profile"]["short_name"], "台積電")  # type: ignore[index]
        self.assertEqual(len(payload["prices"]), 2)  # type: ignore[arg-type]
        self.assertEqual(payload["summary"]["latest_close"], 107)  # type: ignore[index]
        self.assertEqual(payload["quote"]["display_price"], 108)  # type: ignore[index]
        self.assertEqual(payload["quote"]["display_change"], 1)  # type: ignore[index]
        self.assertEqual(payload["monthly_revenues"][0]["year_month"], "2026-05")  # type: ignore[index]
        self.assertEqual(payload["revenue_summary"]["tone"], "positive")  # type: ignore[index]
        self.assertEqual(payload["financial_statements"][0]["eps"], 22.08)  # type: ignore[index]
        self.assertEqual(payload["financial_summary"]["tone"], "positive")  # type: ignore[index]
        self.assertGreater(payload["financial_statements"][0]["roe_percent"], 9)  # type: ignore[index]
        self.assertEqual(len(payload["report"]["sections"]), 6)  # type: ignore[index]
        self.assertEqual(len(payload["validation"]["items"]), 3)  # type: ignore[index]
        self.assertEqual(payload["dividends"][0]["cash_dividend"], 7.0)  # type: ignore[index]
        self.assertEqual(payload["valuation"]["market"]["pe_ratio"], 30.25)  # type: ignore[index]
        self.assertEqual(payload["valuation"]["estimates"][0]["scenario"], "high_yield")  # type: ignore[index]
        self.assertNotIn("便宜價", json.dumps(payload["valuation"], ensure_ascii=False))  # type: ignore[index]
        self.assertNotIn("合理價", json.dumps(payload["valuation"], ensure_ascii=False))  # type: ignore[index]
        self.assertNotIn("昂貴價", json.dumps(payload["valuation"], ensure_ascii=False))  # type: ignore[index]
        self.assertEqual(len(payload["valuation"]["vital_signs"]["facts"]), 4)  # type: ignore[index]
        self.assertGreaterEqual(len(payload["valuation"]["relative"]["methods"]), 1)  # type: ignore[index]
        self.assertTrue(payload["is_watchlisted"])
        self.assertEqual(portfolio_payload["summary"]["positions_count"], 1)  # type: ignore[index]
        self.assertEqual(portfolio_payload["positions"][0]["shares"], 1000)  # type: ignore[index]
        self.assertEqual(portfolio_payload["positions"][0]["latest_close"], 107)  # type: ignore[index]
        self.assertEqual(portfolio_payload["transactions"][0]["note"], "測試買進")  # type: ignore[index]
        self.assertIn("移動平均成本法", portfolio_payload["limitations"][0])  # type: ignore[index]
        self.assertEqual(search_payload["results"][0]["stock_id"], "2330")  # type: ignore[index]
        self.assertEqual(watchlist_payload["items"][0]["profile"]["short_name"], "台積電")  # type: ignore[index]

    def test_glossary_payload_is_available_for_ui_terms(self) -> None:
        payload = glossary_payload()

        self.assertIn("entries", payload)
        self.assertIn("收盤", payload["aliases"])

    def test_cached_local_data_payload_reuses_recent_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                store.upsert_profiles([StockProfile("2330", "台積電", "台積電")])
                store.upsert_daily_prices(
                    [
                        DailyPrice("2330", date(2026, 6, 1), 10, 11, 9, 10, 1000),
                        DailyPrice("2330", date(2026, 6, 2), 10, 12, 10, 11, 1000),
                    ]
                )

                first = build_cached_local_data_payload(store, max_age_seconds=60)
                store.upsert_daily_prices(
                    [DailyPrice("2303", date(2026, 6, 2), 20, 21, 19, 20, 1000)]
                )
                second = build_cached_local_data_payload(store, max_age_seconds=60)
                store.delete_json_cache(LOCAL_DATA_CACHE_KEY)
                refreshed = build_cached_local_data_payload(store, max_age_seconds=60)

        self.assertFalse(first["cache"]["hit"])  # type: ignore[index]
        self.assertTrue(second["cache"]["hit"])  # type: ignore[index]
        self.assertEqual(second["count"], 1)
        self.assertEqual(refreshed["count"], 2)

    def test_build_search_payload_uses_catalog_for_unsynced_stock(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            catalog_path = tmp_path / "stock_catalog.json"
            catalog_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {"stock_id": "2303", "market": "TWSE", "name": "聯電", "short_name": "聯電"},
                            {"stock_id": "2330", "market": "TWSE", "name": "台積電", "short_name": "台積電"},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            db_path = tmp_path / "stock.sqlite3"
            with SQLiteStore(db_path) as store:
                payload = build_search_payload(store, "台積", catalog_path=catalog_path)

                store.upsert_profiles(
                    [
                        StockProfile(
                            stock_id="2330",
                            name="台灣積體電路製造股份有限公司",
                            short_name="台積電",
                        )
                    ]
                )
                synced_payload = build_search_payload(store, "台積", catalog_path=catalog_path)

        self.assertEqual(payload["results"][0]["stock_id"], "2330")  # type: ignore[index]
        self.assertFalse(payload["results"][0]["is_local"])  # type: ignore[index]
        self.assertEqual(synced_payload["results"][0]["stock_id"], "2330")  # type: ignore[index]
        self.assertTrue(synced_payload["results"][0]["is_local"])  # type: ignore[index]

    def test_stock_brief_adds_beginner_sentence_and_watch_items(self) -> None:
        suitability = ValuationSuitability(
            company_type="growth",
            company_type_label="成長股",
            state="low_confidence",
            reasons=["growth_stock", "low_yield"],
            recommended_primary="pe_band",
            recommended_secondary=["revenue_momentum"],
            recommended_avoid=["yield"],
            data_confidence="medium",
            headline="股利法參考性偏低，需搭配其他方法",
        )
        brief = stock_brief_to_json(
            StockProfile(
                stock_id="2330",
                name="台灣積體電路製造股份有限公司",
                short_name="台積電",
                industry_code="24",
            ),
            suitability,
        )
        text = json.dumps(brief, ensure_ascii=False)

        self.assertIn("beginner_sentence", brief)
        self.assertIn("watch_items", brief)
        self.assertIn("營收動能", text)
        self.assertIn("股利不是主軸", text)
        self.assertEqual(contains_forbidden(text), [])

    def test_stock_brief_etf_route_uses_etf_language(self) -> None:
        suitability = ValuationSuitability(
            company_type="etf",
            company_type_label="ETF",
            state="not_applicable",
            reasons=["etf"],
            recommended_primary="distribution_yield_band",
            recommended_secondary=["premium_discount"],
            recommended_avoid=["yield"],
            data_confidence="medium",
            headline="ETF 不適用個股股利法",
        )
        brief = stock_brief_to_json(None, suitability)
        text = json.dumps(brief, ensure_ascii=False)

        self.assertIn("ETF", text)
        self.assertIn("折溢價", text)
        self.assertEqual(contains_forbidden(text), [])


class FakeQuoteProvider:
    def fetch_quote(self, stock_id: str) -> IntradayQuote:
        return IntradayQuote(
            stock_id=stock_id,
            name="台積電",
            full_name="台灣積體電路製造股份有限公司",
            trade_datetime=None,
            current_price=108,
            previous_close=107,
            open_price=106,
            high_price=109,
            low_price=105,
            volume=100,
            best_bid_price=107.5,
            best_ask_price=108,
            bid_prices=(107.5,),
            ask_prices=(108,),
        )


if __name__ == "__main__":
    unittest.main()
