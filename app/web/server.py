from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import threading
import webbrowser
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from app.exporters.excel import (
    build_portfolio_workbook_bytes,
    build_screener_workbook_bytes,
    build_stock_workbook_bytes,
)
from app.news import fetch_company_news
from app.runtime_paths import data_path, ensure_seeded_data_file, static_dir
from app.portfolio import PortfolioCalculationError, calculate_portfolio
from app.portfolio.models import PortfolioTransaction
from app.screener.value import DEFAULT_SCREENER_PATH, refresh_value_screener
from app.store.sqlite_store import SQLiteStore
from app.sync.service import StockSyncService
from app.sync.bulk import BULK_MANAGER
from app.sync.bulk_runner import build_bulk_plan
from app.sync.twse import TwseClient
from app.glossary.service import glossary_payload
from app.quote.providers import TwseMisQuoteProvider
from app.web.api import (
    HISTORICAL_VALUATION_DAYS,
    build_daily_price_payload,
    build_portfolio_payload,
    build_quote_payload,
    build_local_stocks_payload,
    build_local_data_payload,
    build_search_payload,
    build_stock_payload,
    build_value_screener_payload,
    enrich_screener_with_levels,
    build_watchlist_payload,
)
from app.web.sync_batch import normalize_sync_targets

STATIC_DIR = static_dir()
DEFAULT_DB = data_path("stock_translator.sqlite3", writable=True)
CHART_DAYS = 365


class StockTranslatorServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], db_path: Path) -> None:
        super().__init__(server_address, RequestHandler)
        self.db_path = db_path


class RequestHandler(BaseHTTPRequestHandler):
    server: StockTranslatorServer

    def log_message(self, format: str, *args: object) -> None:
        print(f"[web] {self.address_string()} - {format % args}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                self._send_static_file(STATIC_DIR / "index.html")
            elif parsed.path == "/manifest.webmanifest":
                self._send_static_file(STATIC_DIR / "manifest.webmanifest")
            elif parsed.path == "/sw.js":
                self._send_static_file(STATIC_DIR / "sw.js")
            elif parsed.path.startswith("/static/"):
                requested = unquote(parsed.path.removeprefix("/static/"))
                self._send_static_file((STATIC_DIR / requested).resolve())
            elif parsed.path == "/api/local-stocks":
                with SQLiteStore(self.server.db_path) as store:
                    self._send_json(build_local_stocks_payload(store))
            elif parsed.path == "/api/watchlist":
                with SQLiteStore(self.server.db_path) as store:
                    self._send_json(build_watchlist_payload(store))
            elif parsed.path == "/api/glossary":
                self._send_json(glossary_payload())
            elif parsed.path == "/api/portfolio":
                with SQLiteStore(self.server.db_path) as store:
                    self._send_json(build_portfolio_payload(store))
            elif parsed.path == "/api/export/portfolio.xlsx":
                with SQLiteStore(self.server.db_path) as store:
                    content = build_portfolio_workbook_bytes(build_portfolio_payload(store))
                self._send_xlsx(content, "持倉匯出.xlsx")
            elif parsed.path.startswith("/api/export/stocks/") and parsed.path.endswith(".xlsx"):
                stock_id = unquote(parsed.path.removeprefix("/api/export/stocks/")[:-5]).strip()
                if not stock_id:
                    self._send_error(HTTPStatus.BAD_REQUEST, "stock_id is required")
                    return
                with SQLiteStore(self.server.db_path) as store:
                    payload = build_stock_payload(
                        store,
                        stock_id,
                        days=CHART_DAYS,
                        quote_provider=_quote_provider(),
                    )
                    profile = payload.get("profile") or {}
                    short_name = profile.get("short_name") or stock_id
                    content = build_stock_workbook_bytes(payload)
                self._send_xlsx(content, f"{stock_id}-{short_name}.xlsx")
            elif parsed.path == "/api/value-screener":
                with SQLiteStore(self.server.db_path) as store:
                    self._send_json(enrich_screener_with_levels(build_value_screener_payload(), store))
            elif parsed.path == "/api/export/screener.xlsx":
                content = build_screener_workbook_bytes(build_value_screener_payload())
                self._send_xlsx(content, "雷達中心匯出.xlsx")
            elif parsed.path == "/api/local-data":
                with SQLiteStore(self.server.db_path) as store:
                    self._send_json(build_local_data_payload(store))
            elif parsed.path == "/api/bulk-download/status":
                self._send_json(BULK_MANAGER.status())
            elif parsed.path.startswith("/api/news/"):
                stock_id = unquote(parsed.path.removeprefix("/api/news/")).strip()
                if not stock_id:
                    self._send_error(HTTPStatus.BAD_REQUEST, "stock_id is required")
                    return
                params = parse_qs(parsed.query)
                name = params.get("name", [""])[0]
                days = int(params.get("days", ["14"])[0])
                self._send_json(fetch_company_news(stock_id, name, days=days))
            elif parsed.path == "/api/search":
                query = parse_qs(parsed.query).get("q", [""])[0]
                with SQLiteStore(self.server.db_path) as store:
                    self._send_json(build_search_payload(store, query))
            elif parsed.path == "/api/daily-price":
                params = parse_qs(parsed.query)
                with SQLiteStore(self.server.db_path) as store:
                    self._send_json(
                        build_daily_price_payload(
                            store,
                            params.get("stock_id", [""])[0],
                            params.get("date", [""])[0],
                        )
                    )
            elif parsed.path.startswith("/api/stocks/"):
                stock_id = unquote(parsed.path.rsplit("/", 1)[-1]).strip()
                days = int(parse_qs(parsed.query).get("days", ["365"])[0])
                with SQLiteStore(self.server.db_path) as store:
                    self._send_json(
                        build_stock_payload(
                            store,
                            stock_id,
                            days=days,
                            quote_provider=_quote_provider(),
                        )
                    )
            elif parsed.path.startswith("/api/quotes/"):
                stock_id = unquote(parsed.path.rsplit("/", 1)[-1]).strip()
                with SQLiteStore(self.server.db_path) as store:
                    latest = store.get_daily_prices(stock_id, limit=1)
                    latest_close = latest[-1].close if latest else None
                self._send_json(
                    build_quote_payload(
                        stock_id,
                        quote_provider=_quote_provider(),
                        latest_close=latest_close,
                    )
                )
            else:
                self._send_error(HTTPStatus.NOT_FOUND, "Not found")
        except Exception as exc:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/sync":
                body = self._read_json_body()
                stock_id = str(body.get("stock_id", "")).strip()
                lookback_days = int(body.get("lookback_days", HISTORICAL_VALUATION_DAYS))
                if not stock_id:
                    self._send_error(HTTPStatus.BAD_REQUEST, "stock_id is required")
                    return

                with SQLiteStore(self.server.db_path) as store:
                    service = StockSyncService(
                        client=TwseClient(request_interval=0.2),
                        store=store,
                    )
                    result = service.sync_stock_history(
                        stock_id,
                        lookback_days=lookback_days,
                    )
                    payload = build_stock_payload(
                        store,
                        stock_id,
                        days=CHART_DAYS,
                        quote_provider=_quote_provider(),
                    )
                    payload["sync"] = {
                        "rows_written": result.rows_written,
                        "message": result.message,
                        "finished_at": result.finished_at.isoformat(timespec="seconds"),
                    }
                    self._send_json(payload)
            elif parsed.path == "/api/sync/batch":
                body = self._read_json_body()
                stock_ids = normalize_sync_targets(body.get("stock_ids", body.get("stock_id", [])))
                lookback_days = int(body.get("lookback_days", HISTORICAL_VALUATION_DAYS))
                if lookback_days < 1:
                    self._send_error(HTTPStatus.BAD_REQUEST, "lookback_days must be positive")
                    return

                results: list[dict[str, object]] = []
                with SQLiteStore(self.server.db_path) as store:
                    service = StockSyncService(
                        client=TwseClient(request_interval=0.2),
                        store=store,
                    )
                    for stock_id in stock_ids:
                        try:
                            result = service.sync_stock_history(
                                stock_id,
                                lookback_days=lookback_days,
                            )
                        except Exception as exc:
                            results.append(
                                {
                                    "stock_id": stock_id,
                                    "ok": False,
                                    "error": str(exc),
                                }
                            )
                        else:
                            results.append(
                                {
                                    "stock_id": result.stock_id,
                                    "ok": True,
                                    "rows_written": result.rows_written,
                                    "message": result.message,
                                    "finished_at": result.finished_at.isoformat(timespec="seconds"),
                                }
                            )

                succeeded = sum(1 for item in results if item["ok"])
                failed = len(results) - succeeded
                rows_written = sum(int(item.get("rows_written", 0)) for item in results)
                self._send_json(
                    {
                        "requested": len(stock_ids),
                        "succeeded": succeeded,
                        "failed": failed,
                        "rows_written": rows_written,
                        "results": results,
                    }
                )
            elif parsed.path == "/api/institutional/sync":
                body = self._read_json_body()
                stock_id = str(body.get("stock_id", "")).strip()
                lookback_days = int(body.get("lookback_days", 365))
                if not stock_id:
                    self._send_error(HTTPStatus.BAD_REQUEST, "stock_id is required")
                    return
                with SQLiteStore(self.server.db_path) as store:
                    service = StockSyncService(
                        client=TwseClient(request_interval=0.2),
                        store=store,
                    )
                    result = service.sync_institutional(stock_id, lookback_days=lookback_days)
                    payload = build_stock_payload(
                        store,
                        stock_id,
                        days=CHART_DAYS,
                        quote_provider=_quote_provider(),
                    )
                    payload["institutional_sync"] = {
                        "rows_written": result.rows_written,
                        "message": result.message,
                        "finished_at": result.finished_at.isoformat(timespec="seconds"),
                    }
                    self._send_json(payload)
            elif parsed.path == "/api/bulk-download/start":
                body = self._read_json_body()
                lookback_days = int(body.get("lookback_days", 365))
                try:
                    BULK_MANAGER.start(build_bulk_plan(self.server.db_path, lookback_days=lookback_days))
                except RuntimeError as exc:
                    self._send_error(HTTPStatus.CONFLICT, str(exc))
                    return
                self._send_json(BULK_MANAGER.status())
            elif parsed.path == "/api/bulk-download/pause":
                BULK_MANAGER.pause()
                self._send_json(BULK_MANAGER.status())
            elif parsed.path == "/api/bulk-download/resume":
                BULK_MANAGER.resume()
                self._send_json(BULK_MANAGER.status())
            elif parsed.path == "/api/bulk-download/stop":
                BULK_MANAGER.stop()
                self._send_json(BULK_MANAGER.status())
            elif parsed.path == "/api/value-screener/refresh":
                client = TwseClient(request_interval=0.2)
                result = refresh_value_screener(
                    client,
                    output_path=DEFAULT_SCREENER_PATH,
                )
                payload = build_value_screener_payload()
                payload["refresh"] = {
                    "rows": result.rows,
                    "finished_at": result.generated_at.isoformat(timespec="seconds"),
                    "warnings": result.warnings,
                }
                self._send_json(payload)
            elif parsed.path == "/api/watchlist":
                body = self._read_json_body()
                stock_id = str(body.get("stock_id", "")).strip()
                if not stock_id:
                    self._send_error(HTTPStatus.BAD_REQUEST, "stock_id is required")
                    return
                with SQLiteStore(self.server.db_path) as store:
                    store.add_to_watchlist(stock_id)
                    self._send_json(build_watchlist_payload(store))
            elif parsed.path == "/api/portfolio/transactions":
                body = self._read_json_body()
                transaction = self._portfolio_transaction_from_body(body)
                with SQLiteStore(self.server.db_path) as store:
                    self._validate_portfolio_state(store, transaction)
                    transaction_id = store.add_portfolio_transaction(transaction)
                    self._send_json(
                        {
                            "transaction_id": transaction_id,
                            "portfolio": build_portfolio_payload(store),
                        }
                    )
            else:
                self._send_error(HTTPStatus.NOT_FOUND, "Not found")
        except (ValueError, PortfolioCalculationError) as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/portfolio/transactions/"):
                transaction_id = int(unquote(parsed.path.rsplit("/", 1)[-1]).strip())
                body = self._read_json_body()
                transaction = self._portfolio_transaction_from_body(body, transaction_id=transaction_id)
                with SQLiteStore(self.server.db_path) as store:
                    self._validate_portfolio_state(
                        store,
                        transaction,
                        replace_transaction_id=transaction_id,
                    )
                    store.update_portfolio_transaction(transaction)
                    self._send_json(build_portfolio_payload(store))
            else:
                self._send_error(HTTPStatus.NOT_FOUND, "Not found")
        except (ValueError, PortfolioCalculationError) as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
        except KeyError as exc:
            self._send_error(HTTPStatus.NOT_FOUND, str(exc))
        except Exception as exc:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/watchlist/"):
                stock_id = unquote(parsed.path.rsplit("/", 1)[-1]).strip()
                with SQLiteStore(self.server.db_path) as store:
                    store.remove_from_watchlist(stock_id)
                    self._send_json(build_watchlist_payload(store))
            elif parsed.path.startswith("/api/portfolio/transactions/"):
                transaction_id = int(unquote(parsed.path.rsplit("/", 1)[-1]).strip())
                with SQLiteStore(self.server.db_path) as store:
                    self._validate_portfolio_state(
                        store,
                        None,
                        remove_transaction_id=transaction_id,
                    )
                    store.delete_portfolio_transaction(transaction_id)
                    self._send_json(build_portfolio_payload(store))
            else:
                self._send_error(HTTPStatus.NOT_FOUND, "Not found")
        except (ValueError, PortfolioCalculationError) as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
        except KeyError as exc:
            self._send_error(HTTPStatus.NOT_FOUND, str(exc))
        except Exception as exc:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def _read_json_body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _send_static_file(self, path: Path) -> None:
        path = path.resolve()
        if not path.is_file() or STATIC_DIR not in path.parents:
            self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        content = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_xlsx(self, content: bytes, filename: str) -> None:
        safe_filename = quote(filename)
        self.send_response(HTTPStatus.OK)
        self.send_header(
            "Content-Type",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Disposition",
            f"attachment; filename*=UTF-8''{safe_filename}",
        )
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message}, status=status)

    def _portfolio_transaction_from_body(
        self,
        body: dict[str, object],
        *,
        transaction_id: int | None = None,
    ) -> PortfolioTransaction:
        stock_id = str(body.get("stock_id", "")).strip()
        if not stock_id:
            raise ValueError("stock_id is required")
        trade_date_raw = str(body.get("trade_date", "")).strip()
        if not trade_date_raw:
            raise ValueError("trade_date is required")
        side = str(body.get("side", "")).strip()
        if side not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")
        shares = int(body.get("shares", 0))
        price = float(body.get("price", 0))
        fee = float(body.get("fee", 0) or 0)
        tax = float(body.get("tax", 0) or 0)
        return PortfolioTransaction(
            id=transaction_id,
            stock_id=stock_id,
            trade_date=date.fromisoformat(trade_date_raw),
            side=side,  # type: ignore[arg-type]
            shares=shares,
            price=price,
            fee=fee,
            tax=tax,
            note=str(body.get("note", "")).strip(),
        )

    def _validate_portfolio_state(
        self,
        store: SQLiteStore,
        candidate: PortfolioTransaction | None,
        *,
        replace_transaction_id: int | None = None,
        remove_transaction_id: int | None = None,
    ) -> None:
        transactions = store.get_portfolio_transactions()
        if remove_transaction_id is not None and not any(
            item.id == remove_transaction_id for item in transactions
        ):
            raise KeyError(f"portfolio transaction {remove_transaction_id} not found")
        transactions = [
            item for item in transactions
            if item.id not in {replace_transaction_id, remove_transaction_id}
        ]
        if candidate is not None:
            provisional_id = candidate.id
            if provisional_id is None:
                existing_ids = [item.id or 0 for item in transactions]
                provisional_id = (max(existing_ids) if existing_ids else 0) + 1
            candidate = PortfolioTransaction(
                id=provisional_id,
                stock_id=candidate.stock_id,
                trade_date=candidate.trade_date,
                side=candidate.side,
                shares=candidate.shares,
                price=candidate.price,
                fee=candidate.fee,
                tax=candidate.tax,
                note=candidate.note,
            )
            transactions.append(candidate)
        calculate_portfolio(transactions)


def main(argv: list[str] | None = None) -> int:
    _configure_output()
    parser = argparse.ArgumentParser(description="Run the local stock translator UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument(
        "--open",
        action="store_true",
        default=getattr(sys, "frozen", False),
        help="Open the browser.",
    )
    parser.add_argument(
        "--no-open",
        action="store_false",
        dest="open",
        help="Do not open the browser.",
    )
    args = parser.parse_args(argv)

    if args.db == DEFAULT_DB:
        args.db = ensure_seeded_data_file("stock_translator.sqlite3")
    args.db.parent.mkdir(parents=True, exist_ok=True)
    with SQLiteStore(args.db):
        pass

    url = f"http://{args.host}:{args.port}"
    try:
        server = StockTranslatorServer((args.host, args.port), args.db)
    except OSError as exc:
        print(f"Port {args.port} is already in use: {exc}")
        print(f"If Stock Translator is already running, open {url}")
        if args.open:
            webbrowser.open(url)
        return 0

    print(f"Stock Translator UI: {url}")
    print(f"SQLite database: {args.db}")
    print("Press Ctrl+C to stop.")
    if args.open:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()
    return 0


def _configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _quote_provider() -> TwseMisQuoteProvider:
    return TwseMisQuoteProvider(TwseClient(timeout=5.0, request_interval=0.0))


if __name__ == "__main__":
    raise SystemExit(main())
