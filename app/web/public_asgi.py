from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, unquote

from app.glossary.service import glossary_payload
from app.news import fetch_company_news
from app.runtime_paths import data_path, static_dir
from app.store.sqlite_store import SQLiteStore
from app.web.api import (
    build_compare_payload,
    build_daily_price_payload,
    build_forecast_lab_payload,
    build_local_data_payload,
    build_local_stocks_payload,
    build_market_radar_payload,
    build_quote_payload,
    build_search_payload,
    build_stock_payload,
    build_value_screener_payload,
    enrich_screener_with_levels,
)


DEFAULT_DB = data_path("stock_translator.sqlite3", writable=True)
STATIC_DIR = static_dir()
CHART_DAYS = 365


class PublicReadOnlyASGIApp:
    """A minimal ASGI entrypoint for public, read-only deployment.

    The local desktop server exposes personal portfolio/watchlist data and write
    endpoints. This app intentionally keeps a separate route table so a public
    deployment cannot accidentally trigger sync jobs or leak local holdings.
    """

    def __init__(self, db_path: str | Path = DEFAULT_DB, static_path: str | Path = STATIC_DIR) -> None:
        self.db_path = Path(db_path)
        self.static_dir = Path(static_path).resolve()

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        if scope["type"] == "lifespan":
            await self._handle_lifespan(receive, send)
            return
        if scope["type"] != "http":
            await self._send_json(send, {"error": "Unsupported scope"}, HTTPStatus.BAD_REQUEST)
            return

        method = scope.get("method", "GET").upper()
        path = scope.get("path", "/")
        query = parse_qs((scope.get("query_string") or b"").decode("utf-8"))

        try:
            if method != "GET":
                await self._send_json(
                    send,
                    {"error": "Public read-only server does not allow writes."},
                    HTTPStatus.METHOD_NOT_ALLOWED,
                    headers=[(b"allow", b"GET")],
                )
                return
            await self._handle_get(path, query, send)
        except ValueError as exc:
            await self._send_json(send, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001 - public boundary returns JSON instead of tracebacks
            await self._send_json(send, {"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    async def _handle_get(self, path: str, query: dict[str, list[str]], send) -> None:  # type: ignore[no-untyped-def]
        if path == "/":
            await self._send_static_file(send, self.static_dir / "index.html")
            return
        if path == "/manifest.webmanifest":
            await self._send_static_file(send, self.static_dir / "manifest.webmanifest")
            return
        if path == "/sw.js":
            await self._send_static_file(send, self.static_dir / "sw.js")
            return
        if path.startswith("/static/"):
            requested = unquote(path.removeprefix("/static/"))
            await self._send_static_file(send, (self.static_dir / requested).resolve())
            return
        if path == "/api/glossary":
            await self._send_json(send, glossary_payload())
            return
        if path == "/api/watchlist":
            await self._send_json(send, {"items": []})
            return
        if path == "/api/portfolio":
            await self._send_json(send, _empty_public_portfolio_payload())
            return
        if path == "/api/bulk-download/status":
            await self._send_json(
                send,
                {"status": "idle", "running": False, "total": 0, "done": 0, "failed_count": 0},
            )
            return

        with SQLiteStore(self.db_path) as store:
            if path == "/api/local-stocks":
                await self._send_json(send, build_local_stocks_payload(store))
            elif path == "/api/local-data":
                await self._send_json(send, build_local_data_payload(store))
            elif path == "/api/compare":
                await self._send_json(send, build_compare_payload(store, _first(query, "stock_ids")))
            elif path == "/api/value-screener":
                await self._send_json(send, enrich_screener_with_levels(build_value_screener_payload(), store))
            elif path == "/api/market/radar":
                await self._send_json(send, build_market_radar_payload(store))
            elif path == "/api/search":
                await self._send_json(send, build_search_payload(store, _first(query, "q")))
            elif path == "/api/daily-price":
                await self._send_json(
                    send,
                    build_daily_price_payload(
                        store,
                        _first(query, "stock_id"),
                        _first(query, "date"),
                    ),
                )
            elif path.startswith("/api/stocks/") and path.endswith("/forecast-lab"):
                stock_id = unquote(path.removeprefix("/api/stocks/").removesuffix("/forecast-lab")).strip()
                days = int(_first(query, "days", "365"))
                await self._send_json(
                    send,
                    build_forecast_lab_payload(
                        store,
                        stock_id,
                        days=days,
                        quote_provider=None,
                    ),
                )
            elif path.startswith("/api/stocks/"):
                stock_id = unquote(path.rsplit("/", 1)[-1]).strip()
                days = int(_first(query, "days", "365"))
                payload = build_stock_payload(
                    store,
                    stock_id,
                    days=days,
                    quote_provider=None,
                )
                payload["is_watchlisted"] = False
                await self._send_json(send, payload)
            elif path.startswith("/api/quotes/"):
                stock_id = unquote(path.rsplit("/", 1)[-1]).strip()
                latest = store.get_daily_prices(stock_id, limit=1)
                latest_close = latest[-1].close if latest else None
                await self._send_json(
                    send,
                    build_quote_payload(
                        stock_id,
                        quote_provider=None,
                        latest_close=latest_close,
                    ),
                )
            elif path.startswith("/api/news/"):
                stock_id = unquote(path.removeprefix("/api/news/")).strip()
                if not stock_id:
                    raise ValueError("stock_id is required")
                name = _first(query, "name")
                days = int(_first(query, "days", "14"))
                await self._send_json(send, fetch_company_news(stock_id, name, days=days))
            else:
                await self._send_json(send, {"error": "Not found"}, HTTPStatus.NOT_FOUND)

    async def _send_static_file(self, send, path: Path) -> None:  # type: ignore[no-untyped-def]
        path = path.resolve()
        if not path.is_file() or self.static_dir not in path.parents:
            await self._send_json(send, {"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        content = path.read_bytes()
        await self._send_bytes(
            send,
            content,
            HTTPStatus.OK,
            [
                (b"content-type", f"{content_type}; charset=utf-8".encode("utf-8")),
                (b"cache-control", b"public, max-age=300"),
            ],
        )

    async def _send_json(
        self,
        send,  # type: ignore[no-untyped-def]
        payload: object,
        status: HTTPStatus = HTTPStatus.OK,
        *,
        headers: list[tuple[bytes, bytes]] | None = None,
    ) -> None:
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        await self._send_bytes(
            send,
            content,
            status,
            [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"cache-control", b"no-store"),
                *(headers or []),
            ],
        )

    async def _send_bytes(
        self,
        send,  # type: ignore[no-untyped-def]
        content: bytes,
        status: HTTPStatus,
        headers: list[tuple[bytes, bytes]],
    ) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": int(status),
                "headers": [*headers, (b"content-length", str(len(content)).encode("ascii"))],
            }
        )
        await send({"type": "http.response.body", "body": content})

    async def _handle_lifespan(self, receive, send) -> None:  # type: ignore[no-untyped-def]
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return


def create_app(db_path: str | Path = DEFAULT_DB) -> PublicReadOnlyASGIApp:
    return PublicReadOnlyASGIApp(db_path=db_path)


def _first(query: dict[str, list[str]], key: str, default: str = "") -> str:
    values = query.get(key)
    return values[0] if values else default


def _empty_public_portfolio_payload() -> dict[str, object]:
    return {
        "summary": {
            "positions_count": 0,
            "transactions_count": 0,
            "realized_pnl": 0,
            "total_cost_basis": 0,
            "total_market_value": None,
            "total_unrealized_pnl": None,
            "total_unrealized_return_percent": None,
            "missing_price_count": 0,
            "sentence": "公開唯讀模式不載入個人持倉資料。",
            "price_basis": "最近收盤價",
            "cost_method": "不適用",
        },
        "performance": {
            "total_cash_dividends": 0,
            "total_return_amount": 0,
            "total_return_percent": None,
            "xirr_percent": None,
            "dividend_data_complete": True,
            "notes": ["公開唯讀模式不載入個人交易紀錄。"],
            "cash_dividend_events": [],
            "benchmark": None,
        },
        "positions": [],
        "transactions": [],
        "limitations": ["公開唯讀模式不載入個人持倉、自選股或交易紀錄。"],
        "expert_checks": [],
    }


app = create_app()
