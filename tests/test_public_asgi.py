from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from app.models import DailyPrice, StockProfile
from app.portfolio.models import PortfolioTransaction
from app.store.sqlite_store import SQLiteStore
from app.web.public_asgi import PublicReadOnlyASGIApp


class PublicReadOnlyASGITests(unittest.TestCase):
    def test_public_portfolio_and_watchlist_do_not_leak_local_personal_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = _seed_private_db(Path(tmpdir))
            app = PublicReadOnlyASGIApp(db_path=db_path)

            portfolio = _request_json(app, "GET", "/api/portfolio")
            watchlist = _request_json(app, "GET", "/api/watchlist")
            stock = _request_json(app, "GET", "/api/stocks/2330")

        self.assertEqual(portfolio["status"], 200)
        self.assertEqual(portfolio["json"]["positions"], [])
        self.assertEqual(portfolio["json"]["transactions"], [])
        self.assertIn("公開唯讀模式", portfolio["json"]["summary"]["sentence"])
        self.assertEqual(watchlist["status"], 200)
        self.assertEqual(watchlist["json"]["items"], [])
        self.assertEqual(stock["status"], 200)
        self.assertFalse(stock["json"]["is_watchlisted"])
        self.assertNotIn("測試買進", json.dumps(portfolio["json"], ensure_ascii=False))

    def test_public_server_rejects_write_methods(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            app = PublicReadOnlyASGIApp(db_path=Path(tmpdir) / "stock.sqlite3")
            response = _request_json(app, "POST", "/api/watchlist", body=b'{"stock_id":"2330"}')

        self.assertEqual(response["status"], 405)
        self.assertIn("does not allow writes", response["json"]["error"])

    def test_public_search_and_stock_routes_are_read_only_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = _seed_private_db(Path(tmpdir))
            app = PublicReadOnlyASGIApp(db_path=db_path)

            search = _request_json(app, "GET", "/api/search", query={"q": "台積"})
            stock = _request_json(app, "GET", "/api/stocks/2330", query={"days": "30"})

        self.assertEqual(search["status"], 200)
        self.assertEqual(search["json"]["results"][0]["stock_id"], "2330")
        self.assertEqual(stock["status"], 200)
        self.assertEqual(stock["json"]["profile"]["short_name"], "台積電")
        self.assertEqual(stock["json"]["quote"]["status"], "unavailable")


def _seed_private_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "stock.sqlite3"
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
                DailyPrice("2330", date(2026, 6, 10), 100, 105, 99, 102, 10),
                DailyPrice("2330", date(2026, 6, 11), 102, 108, 101, 107, 12),
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
    return db_path


def _request_json(
    app: PublicReadOnlyASGIApp,
    method: str,
    path: str,
    *,
    query: dict[str, str] | None = None,
    body: bytes = b"",
) -> dict[str, object]:
    return asyncio.run(_request_json_async(app, method, path, query=query, body=body))


async def _request_json_async(
    app: PublicReadOnlyASGIApp,
    method: str,
    path: str,
    *,
    query: dict[str, str] | None,
    body: bytes,
) -> dict[str, object]:
    messages: list[dict[str, object]] = []
    sent = False

    async def receive() -> dict[str, object]:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, object]) -> None:
        messages.append(message)

    await app(
        {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": urlencode(query or {}).encode("utf-8"),
            "headers": [],
        },
        receive,
        send,
    )
    start = next(item for item in messages if item["type"] == "http.response.start")
    response_body = b"".join(
        item.get("body", b"") for item in messages if item["type"] == "http.response.body"
    )
    return {
        "status": start["status"],
        "json": json.loads(response_body.decode("utf-8")),
    }
