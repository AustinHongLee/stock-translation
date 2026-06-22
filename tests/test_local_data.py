from __future__ import annotations

import unittest

from app.analyze.local_data import filter_sort_local_data_items


class LocalDataTransformTest(unittest.TestCase):
    def test_filter_stale_and_sort_by_last_date(self) -> None:
        items = [
            {"stock_id": "2330", "price_rows": 10, "last_date": "2026-06-20", "stale_days": 2, "sr_status": "正常"},
            {"stock_id": "2303", "price_rows": 80, "last_date": "2026-06-01", "stale_days": 21, "sr_status": "接近波撐"},
            {"stock_id": "2317", "price_rows": 50, "last_date": "2026-06-10", "stale_days": 12, "sr_status": "接近波壓"},
        ]

        result = filter_sort_local_data_items(items, filter_mode="stale", sort_key="last_date_desc")

        self.assertEqual([item["stock_id"] for item in result], ["2317", "2303"])
        self.assertEqual([item["stock_id"] for item in items], ["2330", "2303", "2317"])

    def test_near_level_filters_and_level_sort(self) -> None:
        items = [
            {"stock_id": "2330", "price_rows": 10, "last_date": "2026-06-20", "stale_days": 2, "sr_status": "接近波撐"},
            {"stock_id": "2303", "price_rows": 80, "last_date": "2026-06-01", "stale_days": 21, "sr_status": "正常"},
            {"stock_id": "2317", "price_rows": 50, "last_date": "2026-06-10", "stale_days": 12, "sr_status": "接近波壓"},
        ]

        support = filter_sort_local_data_items(items, filter_mode="near_support", sort_key="stock_id")
        resistance = filter_sort_local_data_items(items, filter_mode="near_resistance", sort_key="stock_id")
        by_level = filter_sort_local_data_items(items, sort_key="level_status")

        self.assertEqual([item["stock_id"] for item in support], ["2330"])
        self.assertEqual([item["stock_id"] for item in resistance], ["2317"])
        self.assertEqual([item["stock_id"] for item in by_level], ["2317", "2330", "2303"])

    def test_sort_by_price_rows_desc(self) -> None:
        items = [
            {"stock_id": "2330", "price_rows": 10},
            {"stock_id": "2303", "price_rows": 80},
            {"stock_id": "2317", "price_rows": 50},
        ]

        result = filter_sort_local_data_items(items, sort_key="price_rows_desc")

        self.assertEqual([item["stock_id"] for item in result], ["2303", "2317", "2330"])


if __name__ == "__main__":
    unittest.main()
