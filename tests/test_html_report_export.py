from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.exporters.html_report import build_stock_report_html
from app.news.classifier import contains_forbidden


class HtmlReportExportTests(unittest.TestCase):
    def test_stock_report_contains_required_sections_dates_and_no_forbidden_text(self) -> None:
        html = build_stock_report_html(
            _sample_payload(),
            news_payload=_sample_news_payload(),
            generated_at=datetime(2026, 6, 22, 9, 30, tzinfo=timezone.utc),
        )

        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertIn("2330 台積電 個股研究報告", html)
        for section in ("體質總評", "三大法人", "估值情境", "消息 / 地雷雷達", "價量摘要", "重點名詞教學"):
            self.assertIn(section, html)
        self.assertIn("資料日 2026-06-16", html)
        self.assertIn("價格位階 92%", html)
        self.assertIn("不構成投資建議", html)
        self.assertIn("區間統計預設整理最近 60 筆日線", html)
        self.assertEqual([], contains_forbidden(html))

    def test_stock_report_escapes_and_sanitizes_news_titles(self) -> None:
        news = _sample_news_payload()
        news["items"] = [
            {
                "published": "2026-06-16",
                "label": "中性",
                "title": "<script>alert(1)</script> 該買 目標價",
            }
        ]

        html = build_stock_report_html(_sample_payload(), news_payload=news)

        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertEqual([], contains_forbidden(html))


def _sample_payload() -> dict[str, object]:
    prices = [
        {
            "date": f"2026-06-{day:02d}",
            "open": 100 + day,
            "high": 102 + day,
            "low": 99 + day,
            "close": 101 + day,
            "volume": 1_000_000 + day * 1000,
            "trade_value": (101 + day) * (1_000_000 + day * 1000),
        }
        for day in range(1, 17)
    ]
    return {
        "profile": {
            "stock_id": "2330",
            "short_name": "台積電",
            "name": "台灣積體電路製造股份有限公司",
            "market": "TWSE",
        },
        "summary": {
            "latest_close": 117,
            "change": 2,
            "change_percent": 1.74,
            "high": 118,
            "low": 100,
            "price_position": 0.92,
            "rows": len(prices),
            "end_date": "2026-06-16",
        },
        "price_window": {
            "actual_start": "2026-06-01",
            "actual_end": "2026-06-16",
        },
        "prices": prices,
        "assessment": {
            "title": "體質總評",
            "summary": "多數因子偏正向，但仍需搭配資料日期閱讀。",
            "counts": {"bull": 3, "neutral": 2, "bear": 1},
            "factors": [
                {"label": "均線排列", "reading": "MA5 > MA20，短期動能偏強。", "lean": "偏多解讀"},
                {"label": "量能", "reading": "量能正常。", "lean": "中性"},
            ],
        },
        "chips": {
            "available": True,
            "as_of": "2026-06-16",
            "level": "留意",
            "headline": "最新一日三大法人合計淨買超 1,200 張；近 20 日合計淨買超。",
            "reasons": ["近期合計淨買超 8,000 張。"],
            "latest": {
                "foreign_net": 900_000,
                "trust_net": 200_000,
                "dealer_net": 100_000,
                "total_net": 1_200_000,
            },
            "disclaimer": "法人籌碼只呈現三大法人近期買賣超的事實，不預測股價。",
        },
        "valuation": {
            "suitability": {
                "state_label": "股利法參考性低",
                "data_confidence_label": "信心中等",
                "company_type_label": "成長型",
                "recommended": {"primary_label": "本益比敏感度"},
            },
            "relative": {
                "headline": "這是 what-if，不是預測。",
                "methods": [
                    {
                        "title": "本益比敏感度",
                        "warning": "PE 敏感度不判斷價格高低。",
                        "estimates": [
                            {"label": "市場少付 20%", "price": 96},
                            {"label": "目前倍數", "price": 117},
                        ],
                    }
                ],
            },
            "bands": {
                "pe": {
                    "available": True,
                    "current": 22.5,
                    "current_percentile": 61,
                    "sample_size": 260,
                },
                "pb": {
                    "available": True,
                    "current": 5.2,
                    "current_percentile": 55,
                    "sample_size": 260,
                },
            },
        },
        "report": {"sections": []},
    }


def _sample_news_payload() -> dict[str, object]:
    return {
        "status": "available",
        "generated_at": "2026-06-16T08:00:00+00:00",
        "overall": "近 14 天共 2 則新聞，消息正反互見、沒有一面倒。",
        "risk_summary": {
            "score": 1,
            "level": "低",
            "reasons": ["未偵測到重大財務或治理風險詞。"],
            "windows": {"d7": 0, "d14": 1, "d45": 1},
            "heating": False,
        },
        "items": [
            {"published": "2026-06-15", "label": "利多", "title": "台積電公布新製程量產時程"},
            {"published": "2026-06-14", "label": "中性", "title": "台積電法說會說明資本支出"},
        ],
        "disclaimer": "消息整理為多來源公開新聞的關鍵字歸類，僅供快速了解，非投資建議、不預測股價。",
    }


if __name__ == "__main__":
    unittest.main()
