from __future__ import annotations

import re
import unittest
from datetime import date

from app.analyze.daily_digest import build_daily_digest
from app.models import InstitutionalTrade

FORBIDDEN = re.compile(
    r"會漲|會跌|該買|該賣|買進|賣出|目標價|勝率|停損|停利|保證|必漲|必跌|明牌|買點|賣點|看多|看空"
)


def _item(
    stock_id: str,
    name: str,
    *,
    change_percent: float | None,
    latest_date: str | None = "2026-07-13",
    close: float | None = 100.0,
    stale_days: int | None = 1,
    level_status: str = "區間中段",
) -> dict:
    return {
        "stock_id": stock_id,
        "profile": {"short_name": name},
        "board": {
            "name": name,
            "latest": {"close": close, "date": latest_date, "change_percent": change_percent},
            "data": {"rows": 200, "stale_days": stale_days},
            "level": {"status": level_status},
        },
    }


def _trades(stock_id: str, days: list[tuple[str, int, int]]) -> list[InstitutionalTrade]:
    """days: [(date, foreign_net, total_net)] 由新到舊或亂序皆可。"""
    return [
        InstitutionalTrade(
            stock_id=stock_id,
            date=date.fromisoformat(day),
            foreign_net=foreign,
            trust_net=0,
            dealer_net=0,
            total_net=total,
        )
        for day, foreign, total in days
    ]


class DailyDigestTests(unittest.TestCase):
    def test_empty_watchlist_returns_none(self) -> None:
        self.assertIsNone(build_daily_digest([]))

    def test_counts_movers_and_headline(self) -> None:
        digest = build_daily_digest(
            [
                _item("2330", "台積電", change_percent=2.31, level_status="接近波壓"),
                _item("2412", "中華電", change_percent=-0.4),
                _item("2603", "長榮", change_percent=-3.1),
                _item("1101", "台泥", change_percent=0.0),
            ]
        )
        assert digest is not None
        self.assertEqual(digest["date"], "2026-07-13")
        self.assertIn("自選 4 檔", digest["trading_summary"])
        self.assertIn("1 漲 2 跌 1 平", digest["trading_summary"])
        movers = digest["movers"]
        self.assertEqual([m["stock_id"] for m in movers], ["2603", "2330"])  # |chg| 降序
        self.assertEqual(movers[1]["note"], "接近波壓")
        self.assertIn("長榮", digest["headline"])
        self.assertIn("-3.10%", digest["headline"])
        self.assertFalse(digest["quiet"])

    def test_quiet_day(self) -> None:
        digest = build_daily_digest(
            [
                _item("2330", "台積電", change_percent=0.5),
                _item("2412", "中華電", change_percent=-0.2),
            ]
        )
        assert digest is not None
        self.assertTrue(digest["quiet"])
        self.assertIn("平靜", digest["headline"])
        self.assertEqual(digest["movers"], [])

    def test_chips_streak_lines_prefer_foreign_and_min_days(self) -> None:
        chips = {
            # 外資連 3 天買超（total 同向）→ 用外資行
            "2330": _trades(
                "2330",
                [("2026-07-13", 500, 700), ("2026-07-10", 300, 100), ("2026-07-09", 200, 50)],
            ),
            # 外資只連 2 天、但三大合計連 3 天賣超 → 用三大行
            "2603": _trades(
                "2603",
                [("2026-07-13", -100, -400), ("2026-07-10", 100, -200), ("2026-07-09", -50, -100)],
            ),
            # 只有 2 天同向 → 不成行
            "2412": _trades("2412", [("2026-07-13", 100, 100), ("2026-07-10", 200, 200)]),
        }
        digest = build_daily_digest(
            [
                _item("2330", "台積電", change_percent=1.0),
                _item("2603", "長榮", change_percent=-1.0),
                _item("2412", "中華電", change_percent=0.1),
            ],
            chips,
        )
        assert digest is not None
        lines = digest["chips_lines"]
        self.assertEqual(len(lines), 2)
        self.assertIn("外資連 3 天買超 台積電", lines)
        self.assertIn("三大法人連 3 天賣超 長榮", lines)

    def test_attention_lines_for_stale_and_missing(self) -> None:
        digest = build_daily_digest(
            [
                _item("2330", "台積電", change_percent=1.0, stale_days=15),
                _item("9999", "沒資料", change_percent=None, latest_date=None, close=None, stale_days=None),
            ]
        )
        assert digest is not None
        self.assertIn("1 檔本地資料日期偏舊，先同步再看。", digest["attention"])
        self.assertIn("1 檔還沒有本地日線，可先按同步。", digest["attention"])
        self.assertIn("1 檔無最新資料", digest["trading_summary"])

    def test_all_texts_pass_forbidden_scan(self) -> None:
        chips = {
            "2330": _trades(
                "2330",
                [("2026-07-13", 500, 700), ("2026-07-10", 300, 100), ("2026-07-09", 200, 50)],
            )
        }
        digest = build_daily_digest(
            [
                _item("2330", "台積電", change_percent=4.2, level_status="接近波壓"),
                _item("2603", "長榮", change_percent=-2.5),
                _item("9999", "沒資料", change_percent=None, latest_date=None, stale_days=None),
            ],
            chips,
        )
        assert digest is not None
        texts = [
            digest["headline"],
            digest["trading_summary"],
            digest["disclaimer"],
            *digest["chips_lines"],
            *digest["attention"],
            *[str(m["note"]) for m in digest["movers"]],
        ]
        for text in texts:
            self.assertIsNone(FORBIDDEN.search(str(text)), f"forbidden word in: {text}")


if __name__ == "__main__":
    unittest.main()
