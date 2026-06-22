from __future__ import annotations

import unittest
from datetime import date, timedelta

from app.analyze.stock_compare import (
    build_stock_comparison,
    build_stock_comparison_item,
    normalize_compare_stock_ids,
)
from app.models import DailyPrice, FinancialStatement, InstitutionalTrade, MonthlyRevenue, StockProfile


class StockCompareTests(unittest.TestCase):
    def test_comparison_item_reports_price_chips_assessment_and_financials(self) -> None:
        payload = build_stock_comparison(
            [
                {
                    "stock_id": "2330",
                    "profile": StockProfile("2330", "台灣積體電路製造股份有限公司", "台積電"),
                    "prices": _prices("2330", date(2026, 5, 1), [100 + i for i in range(25)]),
                    "institutional_trades": _trades("2330", date(2026, 5, 1), [1100] * 20),
                    "monthly_revenues": [_revenue("2330", 30.5)],
                    "financial_statements": [_financial("2330", eps=22.08, parent_net_income=572_479_752)],
                },
                {
                    "stock_id": "2317",
                    "profile": StockProfile("2317", "鴻海精密工業股份有限公司", "鴻海"),
                    "prices": _prices("2317", date(2026, 5, 1), [200 - i for i in range(25)]),
                    "institutional_trades": _trades("2317", date(2026, 5, 1), [-2500] * 20),
                    "monthly_revenues": [_revenue("2317", -8.2)],
                    "financial_statements": [_financial("2317", eps=1.25, parent_net_income=20_000_000)],
                },
            ]
        )

        first = payload["items"][0]  # type: ignore[index]
        second = payload["items"][1]  # type: ignore[index]
        self.assertEqual(payload["count"], 2)
        self.assertEqual(first["profile"]["short_name"], "台積電")  # type: ignore[index]
        self.assertEqual(first["price"]["latest_close"], 124.0)  # type: ignore[index]
        self.assertAlmostEqual(first["price"]["change_percent"], 0.813, places=3)  # type: ignore[index]
        self.assertEqual(first["chips"]["sum_20_lots"], 22)  # type: ignore[index]
        self.assertEqual(first["chips"]["tone"], "neutral")  # type: ignore[index]
        self.assertEqual(first["financial"]["quarter"], "2026Q1")  # type: ignore[index]
        self.assertEqual(first["financial"]["eps"], 22.08)  # type: ignore[index]
        self.assertEqual(first["assessment"]["label"], "體質中性")  # type: ignore[index]
        self.assertEqual(first["assessment"]["bear"], 3)  # type: ignore[index]
        self.assertEqual(second["chips"]["sum_20_lots"], -50)  # type: ignore[index]
        self.assertEqual(second["chips"]["tone"], "caution")  # type: ignore[index]
        self.assertIn("不預測股價", payload["disclaimer"])

    def test_normalizes_dedupes_and_limits_compare_ids(self) -> None:
        ids = normalize_compare_stock_ids("2330, 2317 2330/2454|3008")

        self.assertEqual(ids, ["2330", "2317", "2454"])

    def test_missing_local_data_is_explicit(self) -> None:
        item = build_stock_comparison_item({"stock_id": "9999"})

        self.assertEqual(item["price"]["latest_close"], None)  # type: ignore[index]
        self.assertEqual(item["chips"]["level"], "資料不足")  # type: ignore[index]
        self.assertEqual(item["assessment"]["label"], "資料不足")  # type: ignore[index]
        self.assertFalse(item["financial"]["available"])  # type: ignore[index]


def _prices(stock_id: str, start: date, closes: list[float]) -> list[DailyPrice]:
    return [
        DailyPrice(
            stock_id=stock_id,
            date=start + timedelta(days=index),
            open=close - 0.5,
            high=close + 1,
            low=close - 1,
            close=close,
            volume=1_000_000 + index,
        )
        for index, close in enumerate(closes)
    ]


def _trades(stock_id: str, start: date, totals: list[int]) -> list[InstitutionalTrade]:
    return [
        InstitutionalTrade(
            stock_id=stock_id,
            date=start + timedelta(days=index),
            foreign_net=total,
            trust_net=0,
            dealer_net=0,
            total_net=total,
        )
        for index, total in enumerate(totals)
    ]


def _revenue(stock_id: str, yoy_percent: float) -> MonthlyRevenue:
    return MonthlyRevenue(
        stock_id=stock_id,
        year_month="2026-05",
        company_name=stock_id,
        industry="半導體業",
        current_month_revenue=416_975_163,
        previous_month_revenue=410_725_118,
        last_year_month_revenue=320_515_951,
        mom_percent=1.52,
        yoy_percent=yoy_percent,
        cumulative_revenue=1_961_803_721,
        cumulative_last_year_revenue=1_509_336_555,
        cumulative_yoy_percent=29.98,
        source_updated_at=date(2026, 6, 11),
    )


def _financial(stock_id: str, *, eps: float, parent_net_income: int) -> FinancialStatement:
    return FinancialStatement(
        stock_id=stock_id,
        year=2026,
        quarter=1,
        company_name=stock_id,
        revenue=1_134_103_440,
        gross_profit=751_295_421,
        operating_income=658_966_142,
        non_operating_income_expense=28_833_545,
        pre_tax_income=687_799_687,
        net_income=572_801_304,
        parent_net_income=parent_net_income,
        eps=eps,
        total_assets=8_660_949_685,
        total_liabilities=2_728_560_764,
        parent_equity=5_890_960_252,
        total_equity=5_932_388_921,
        book_value_per_share=227.17,
        source_updated_at=date(2026, 6, 12),
    )


if __name__ == "__main__":
    unittest.main()
