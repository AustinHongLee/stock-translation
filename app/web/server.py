from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import threading
import time
import webbrowser
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from app.exporters.excel import (
    build_portfolio_workbook_bytes,
    build_screener_workbook_bytes,
    build_stock_workbook_bytes,
)
from app.exporters.html_report import assert_report_has_no_forbidden, build_stock_report_html
from app.news import fetch_company_news
from app.runtime_paths import (
    data_dir,
    data_path,
    ensure_seeded_data_file,
    external_root,
    migrate_legacy_data,
    seed_dir,
    static_dir,
)
from app.store.legacy_import import copy_legacy_snapshot, import_legacy_data, legacy_import_status
from app.store.seed_merge import applied_seed_version, maybe_merge_seed, seed_manifest_version
from app.update.checker import check_for_update
from app.update.installer import prepare_update, start_prepared_update
from app.version import APP_VERSION
from app.portfolio import PortfolioCalculationError, calculate_portfolio
from app.portfolio.models import PortfolioTransaction
from app.screener.value import DEFAULT_SCREENER_PATH, refresh_value_screener
from app.store.sqlite_store import SQLiteStore
from app.sync.service import StockSyncService, SyncResult
from app.sync.bulk import BULK_MANAGER
from app.sync.bulk_runner import BULK_RUN_KEY, QUIET_REQUEST_INTERVAL, build_bulk_plan
from app.sync.twse import TwseClient
from app.glossary.service import glossary_payload
from app.quote.providers import TwseMisQuoteProvider
from app.web.api import (
    HISTORICAL_VALUATION_DAYS,
    LOCAL_DATA_CACHE_KEY,
    build_compare_payload,
    build_daily_price_payload,
    build_forecast_lab_payload,
    build_indicator_catalog_payload,
    build_portfolio_payload,
    build_quote_payload,
    build_local_stocks_payload,
    build_market_radar_payload,
    build_cached_local_data_payload,
    build_chart_annotations_payload,
    build_search_payload,
    build_sync_freshness_payload,
    build_stock_payload,
    build_indicator_prefs_payload,
    build_value_screener_payload,
    enrich_screener_with_levels,
    build_watchlist_payload,
    create_chart_annotation_payload,
    delete_chart_annotation_payload,
    save_indicator_prefs_payload,
    update_chart_annotation_payload,
)
from app.web.sync_batch import normalize_sync_targets

STATIC_DIR = static_dir()
DEFAULT_DB = data_path("stock_translator.sqlite3", writable=True)
CHART_DAYS = 365
TWSE_FETCH_DURING_BULK_MESSAGE = "全市場資料下載進行中，請先暫停、停止或等完成後再更新雷達/同步個股。"
TWSE_FETCH_BLOCKED_DURING_BULK = {
    "/api/sync",
    "/api/sync/batch",
    "/api/institutional/sync",
    "/api/value-screener/refresh",
}
UPDATE_CHECK_CACHE_SECONDS = 300
_UPDATE_CHECK_CACHE: dict[str, object] = {"checked_at": 0.0, "payload": None}
# 背景安靜同步：app 開著時每隔一段時間自動「補最新 + 慢速補歷史」。
QUIET_SYNC_STATE_KEY = "quiet_sync_state"
QUIET_SYNC_MIN_INTERVAL_HOURS = 4.0
QUIET_SYNC_LOOP_SECONDS = 1800.0


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
            elif parsed.path == "/api/indicators/catalog":
                self._send_json(build_indicator_catalog_payload())
            elif parsed.path == "/api/app-info":
                self._send_json(_app_info_payload(self.server.db_path))
            elif parsed.path == "/api/update/check":
                params = parse_qs(parsed.query)
                force = (params.get("force") or ["0"])[0] in {"1", "true", "yes"}
                self._send_json(_latest_update_info(force=force))
            elif parsed.path == "/api/data/legacy-import":
                self._send_json(_legacy_import_payload())
            elif parsed.path == "/api/indicator-prefs":
                with SQLiteStore(self.server.db_path) as store:
                    self._send_json(build_indicator_prefs_payload(store))
            elif parsed.path == "/api/portfolio":
                with SQLiteStore(self.server.db_path) as store:
                    self._send_json(build_portfolio_payload(store))
            elif parsed.path == "/api/compare":
                params = parse_qs(parsed.query)
                stock_ids = (params.get("stock_ids") or params.get("ids") or [""])[0]
                with SQLiteStore(self.server.db_path) as store:
                    self._send_json(build_compare_payload(store, stock_ids))
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
            elif parsed.path.startswith("/api/export/stocks/") and parsed.path.endswith(".html"):
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
                    short_name = str(profile.get("short_name") or stock_id)
                news_payload = _report_news_payload(stock_id, short_name)
                content = build_stock_report_html(payload, news_payload=news_payload)
                assert_report_has_no_forbidden(content)
                self._send_html(content, f"{stock_id}-{short_name}-個股研究報告.html")
            elif parsed.path == "/api/value-screener":
                with SQLiteStore(self.server.db_path) as store:
                    self._send_json(enrich_screener_with_levels(build_value_screener_payload(), store))
            elif parsed.path == "/api/market/radar":
                with SQLiteStore(self.server.db_path) as store:
                    self._send_json(build_market_radar_payload(store))
            elif parsed.path == "/api/export/screener.xlsx":
                content = build_screener_workbook_bytes(build_value_screener_payload())
                self._send_xlsx(content, "雷達中心匯出.xlsx")
            elif parsed.path == "/api/local-data":
                with SQLiteStore(self.server.db_path) as store:
                    self._send_json(build_cached_local_data_payload(store))
            elif parsed.path == "/api/bulk-download/status":
                self._send_json(_bulk_status(self.server.db_path))
            elif parsed.path.startswith("/api/sync/freshness/"):
                stock_id = unquote(parsed.path.rsplit("/", 1)[-1]).strip()
                with SQLiteStore(self.server.db_path) as store:
                    self._send_json(build_sync_freshness_payload(store, stock_id))
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
            elif parsed.path.startswith("/api/stocks/") and parsed.path.endswith("/annotations"):
                stock_id = unquote(parsed.path.removeprefix("/api/stocks/").removesuffix("/annotations")).strip()
                with SQLiteStore(self.server.db_path) as store:
                    self._send_json(build_chart_annotations_payload(store, stock_id))
            elif parsed.path.startswith("/api/stocks/") and parsed.path.endswith("/forecast-lab"):
                stock_id = unquote(parsed.path.removeprefix("/api/stocks/").removesuffix("/forecast-lab")).strip()
                days = int(parse_qs(parsed.query).get("days", ["365"])[0])
                with SQLiteStore(self.server.db_path) as store:
                    self._send_json(build_forecast_lab_payload(store, stock_id, days=days, quote_provider=None))
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
        except ValueError as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if _bulk_blocks_twse_fetch(parsed.path):
                self._send_error(HTTPStatus.CONFLICT, TWSE_FETCH_DURING_BULK_MESSAGE)
                return
            if parsed.path.startswith("/api/stocks/") and parsed.path.endswith("/annotations"):
                stock_id = unquote(parsed.path.removeprefix("/api/stocks/").removesuffix("/annotations")).strip()
                body = self._read_json_body()
                with SQLiteStore(self.server.db_path) as store:
                    self._send_json(create_chart_annotation_payload(store, stock_id, body), status=HTTPStatus.CREATED)
            elif parsed.path == "/api/sync":
                body = self._read_json_body()
                stock_id = str(body.get("stock_id", "")).strip()
                lookback_days = int(body.get("lookback_days", HISTORICAL_VALUATION_DAYS))
                skip_if_current = bool(body.get("skip_if_current", False))
                if not stock_id:
                    self._send_error(HTTPStatus.BAD_REQUEST, "stock_id is required")
                    return

                with SQLiteStore(self.server.db_path) as store:
                    freshness = build_sync_freshness_payload(store, stock_id)
                    target_date = _date_or_none(
                        freshness.get("target_latest_date") or freshness.get("reference_latest_date")
                    )
                    if skip_if_current and freshness.get("can_skip_sync"):
                        payload = build_stock_payload(
                            store,
                            stock_id,
                            days=CHART_DAYS,
                            quote_provider=_quote_provider(),
                        )
                        payload["sync"] = {
                            "skipped": True,
                            "rows_written": 0,
                            "message": freshness["message"],
                            "user_message": freshness["message"],
                            "status": "skipped",
                            "current": True,
                            "needs_retry": False,
                            "finished_at": datetime.now().isoformat(timespec="seconds"),
                            "freshness": freshness,
                            "gap": (freshness.get("daily_price") or {}).get("gap"),
                            "coverage": (freshness.get("daily_price") or {}).get("coverage"),
                        }
                        self._send_json(payload)
                        return
                    service = StockSyncService(
                        client=TwseClient(request_interval=0.2),
                        store=store,
                    )
                    result = service.sync_stock_history(
                        stock_id,
                        lookback_days=lookback_days,
                        target_date=target_date,
                    )
                    payload = build_stock_payload(
                        store,
                        stock_id,
                        days=CHART_DAYS,
                        quote_provider=_quote_provider(),
                    )
                    payload["sync"] = {
                        "skipped": False,
                        "rows_written": result.rows_written,
                        "message": result.message,
                        **_sync_outcome_payload(result),
                        "finished_at": result.finished_at.isoformat(timespec="seconds"),
                        "freshness": freshness,
                        "gap": result.gap_plan,
                        "coverage": result.coverage,
                        "post_status": result.post_status,
                        "price_warning_count": result.price_warning_count,
                        "first_price_warning": result.first_price_warning,
                    }
                    store.delete_json_cache(LOCAL_DATA_CACHE_KEY)
                    self._send_json(payload)
            elif parsed.path == "/api/sync/batch":
                body = self._read_json_body()
                stock_ids = normalize_sync_targets(body.get("stock_ids", body.get("stock_id", [])))
                lookback_days = int(body.get("lookback_days", HISTORICAL_VALUATION_DAYS))
                skip_if_current = bool(body.get("skip_if_current", False))
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
                            freshness = build_sync_freshness_payload(store, stock_id)
                            target_date = _date_or_none(
                                freshness.get("target_latest_date") or freshness.get("reference_latest_date")
                            )
                            if skip_if_current and freshness.get("can_skip_sync"):
                                results.append(
                                    {
                                        "stock_id": stock_id,
                                        "ok": True,
                                        "skipped": True,
                                        "rows_written": 0,
                                        "message": freshness["message"],
                                        "user_message": freshness["message"],
                                        "status": "skipped",
                                        "current": True,
                                        "needs_retry": False,
                                        "finished_at": datetime.now().isoformat(timespec="seconds"),
                                        "freshness": freshness,
                                        "gap": (freshness.get("daily_price") or {}).get("gap"),
                                        "coverage": (freshness.get("daily_price") or {}).get("coverage"),
                                    }
                                )
                                continue
                            result = service.sync_stock_history(
                                stock_id,
                                lookback_days=lookback_days,
                                target_date=target_date,
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
                                    "skipped": False,
                                    "rows_written": result.rows_written,
                                    "message": result.message,
                                    **_sync_outcome_payload(result),
                                    "finished_at": result.finished_at.isoformat(timespec="seconds"),
                                    "freshness": freshness,
                                    "gap": result.gap_plan,
                                    "coverage": result.coverage,
                                    "post_status": result.post_status,
                                    "price_warning_count": result.price_warning_count,
                                    "first_price_warning": result.first_price_warning,
                                }
                            )

                    store.delete_json_cache(LOCAL_DATA_CACHE_KEY)
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
                    freshness = build_sync_freshness_payload(store, stock_id)
                    target_date = _date_or_none(
                        freshness.get("target_latest_date") or freshness.get("reference_latest_date")
                    )
                    service = StockSyncService(
                        client=TwseClient(request_interval=0.2),
                        store=store,
                    )
                    result = service.sync_institutional(
                        stock_id,
                        lookback_days=lookback_days,
                        target_date=target_date,
                    )
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
                        "skipped": result.skipped,
                        "gap": result.gap_plan,
                        "coverage": result.coverage,
                        "freshness": freshness,
                    }
                    self._send_json(payload)
            elif parsed.path == "/api/bulk-download/start":
                body = self._read_json_body()
                lookback_days = int(body.get("lookback_days", 365))
                _preempt_quiet_run(BULK_MANAGER)
                try:
                    BULK_MANAGER.start(build_bulk_plan(self.server.db_path, lookback_days=lookback_days))
                except RuntimeError as exc:
                    self._send_error(HTTPStatus.CONFLICT, str(exc))
                    return
                self._send_json(_bulk_status(self.server.db_path))
            elif parsed.path == "/api/bulk-download/retry-failed":
                body = self._read_json_body()
                lookback_days = int(body.get("lookback_days", 365))
                with SQLiteStore(self.server.db_path) as store:
                    summary = store.get_bulk_progress_summary(BULK_RUN_KEY)
                    if int(summary.get("failed_count", 0)) <= 0:
                        self._send_error(HTTPStatus.BAD_REQUEST, "目前沒有失敗清單可重試")
                        return
                _preempt_quiet_run(BULK_MANAGER)
                try:
                    BULK_MANAGER.start(
                        build_bulk_plan(
                            self.server.db_path,
                            lookback_days=lookback_days,
                            retry_failed_only=True,
                        )
                    )
                except RuntimeError as exc:
                    self._send_error(HTTPStatus.CONFLICT, str(exc))
                    return
                self._send_json(_bulk_status(self.server.db_path))
            elif parsed.path == "/api/bulk-download/pause":
                BULK_MANAGER.pause()
                self._send_json(_bulk_status(self.server.db_path))
            elif parsed.path == "/api/bulk-download/resume":
                BULK_MANAGER.resume()
                self._send_json(_bulk_status(self.server.db_path))
            elif parsed.path == "/api/bulk-download/stop":
                BULK_MANAGER.stop()
                self._send_json(_bulk_status(self.server.db_path))
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
            elif parsed.path == "/api/update/download":
                body = self._read_json_body()
                update_info = _latest_update_info(force=bool(body.get("force")))
                if body.get("url"):
                    update_info = {
                        **update_info,
                        "url": str(body.get("url") or ""),
                        "manual_url": str(body.get("url") or ""),
                        "latest": str(body.get("latest") or update_info.get("latest") or ""),
                        "asset_name": str(body.get("asset_name") or update_info.get("asset_name") or ""),
                        "size": int(body.get("size") or update_info.get("size") or 0),
                        "sha256": str(body.get("sha256") or update_info.get("sha256") or ""),
                        "sha256_url": str(body.get("sha256_url") or update_info.get("sha256_url") or ""),
                    }
                manual_url = str(update_info.get("manual_url") or update_info.get("url") or "")
                if not manual_url:
                    self._send_error(HTTPStatus.BAD_REQUEST, "目前沒有可下載的新版 zip。")
                    return
                if not getattr(sys, "frozen", False):
                    self._send_json(
                        {
                            "ok": False,
                            "started": False,
                            "will_restart": False,
                            "manual_url": manual_url,
                            "latest": update_info.get("latest") or "",
                            "message": "開發模式不執行自動換版；請用「直接下載」或打包後測試。",
                        }
                    )
                    return
                prepared = prepare_update(update_info)
                start_prepared_update(prepared)
                self._send_json(
                    {
                        "ok": True,
                        "started": True,
                        "will_restart": True,
                        "manual_url": manual_url,
                        "latest": prepared.latest,
                        "message": "下載完成，更新程式已啟動；本程式即將關閉並重開。",
                    },
                    status=HTTPStatus.ACCEPTED,
                )
                threading.Timer(0.5, self.server.shutdown).start()
            elif parsed.path == "/api/data/legacy-import":
                if not getattr(sys, "frozen", False):
                    self._send_json({"ok": False, "available": False, "reason": "dev_mode"})
                    return
                legacy_db, current_db, legacy_dir = _legacy_import_paths()
                summary = import_legacy_data(legacy_db, current_db)
                snapshot_copied = copy_legacy_snapshot(legacy_dir, data_dir())
                with SQLiteStore(current_db) as store:
                    store.delete_json_cache(LOCAL_DATA_CACHE_KEY)
                _write_legacy_import_dismissed()
                self._send_json({"ok": True, **summary, "snapshot_copied": snapshot_copied})
            elif parsed.path == "/api/data/legacy-import/dismiss":
                _write_legacy_import_dismissed()
                self._send_json({"ok": True})
            elif parsed.path == "/api/data/seed/apply":
                result = _apply_seed_now(self.server.db_path, force=True)
                self._send_json(
                    {
                        "ok": bool(result.get("applied")),
                        **result,
                        "message": _seed_merge_message(result, manual=True),
                        "app_info": _app_info_payload(self.server.db_path),
                    }
                )
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
            if parsed.path == "/api/indicator-prefs":
                body = self._read_json_body()
                with SQLiteStore(self.server.db_path) as store:
                    self._send_json(save_indicator_prefs_payload(store, body))
            elif parsed.path.startswith("/api/portfolio/transactions/"):
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

    def do_PATCH(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/stocks/") and "/annotations/" in parsed.path:
                prefix, annotation_id_text = parsed.path.rsplit("/annotations/", 1)
                stock_id = unquote(prefix.removeprefix("/api/stocks/")).strip()
                annotation_id = int(unquote(annotation_id_text).strip())
                body = self._read_json_body()
                with SQLiteStore(self.server.db_path) as store:
                    self._send_json(update_chart_annotation_payload(store, stock_id, annotation_id, body))
            else:
                self._send_error(HTTPStatus.NOT_FOUND, "Not found")
        except ValueError as exc:
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
            elif parsed.path.startswith("/api/stocks/") and "/annotations/" in parsed.path:
                prefix, annotation_id_text = parsed.path.rsplit("/annotations/", 1)
                stock_id = unquote(prefix.removeprefix("/api/stocks/")).strip()
                annotation_id = int(unquote(annotation_id_text).strip())
                with SQLiteStore(self.server.db_path) as store:
                    self._send_json(delete_chart_annotation_payload(store, stock_id, annotation_id))
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

    def _send_html(self, content: str, filename: str) -> None:
        raw = content.encode("utf-8")
        safe_filename = quote(filename)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Disposition",
            f"inline; filename*=UTF-8''{safe_filename}",
        )
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

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
    parser.add_argument(
        "--apply-seed",
        action="store_true",
        help="Apply bundled public seed data to the local database and exit.",
    )
    parser.add_argument(
        "--no-auto-sync",
        action="store_false",
        dest="auto_sync",
        default=True,
        help="Disable the quiet background data sync loop.",
    )
    args = parser.parse_args(argv)

    if args.db == DEFAULT_DB:
        migrate_legacy_data("stock_translator.sqlite3")
        args.db = ensure_seeded_data_file("stock_translator.sqlite3")
    args.db.parent.mkdir(parents=True, exist_ok=True)
    with SQLiteStore(args.db):
        pass
    if args.apply_seed:
        result = _apply_seed_now(args.db, force=True)
        print(_seed_merge_message(result, manual=True))
        return 0
    _start_seed_merge_if_needed(args.db)
    if args.auto_sync:
        _start_quiet_sync_loop(args.db)

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


def _preempt_quiet_run(manager) -> None:
    """使用者主動下載時先讓路：停掉正在跑的背景安靜同步。"""
    status = manager.status()
    if status.get("running") and status.get("mode") == "quiet":
        manager.stop()
        manager.join(15)


def _quiet_sync_due(store, *, now: datetime | None = None) -> bool:
    """距離上次背景同步超過間隔才 due；沒有紀錄視為 due。"""
    cached = store.get_json_cache(QUIET_SYNC_STATE_KEY)
    if cached is None:
        return True
    _payload, updated_at = cached
    now = now or datetime.now()
    return (now - updated_at).total_seconds() >= QUIET_SYNC_MIN_INTERVAL_HOURS * 3600


def _run_quiet_sync_once(db_path: Path) -> bool:
    """時間到且沒有任務在跑，就啟動一輪背景安靜同步（補最新 + 慢速補歷史）。"""
    status = BULK_MANAGER.status()
    if status.get("running") or status.get("paused"):
        return False
    with SQLiteStore(db_path) as store:
        if not _quiet_sync_due(store):
            return False
        store.set_json_cache(
            QUIET_SYNC_STATE_KEY,
            {"last": datetime.now().isoformat(timespec="seconds")},
        )
    try:
        BULK_MANAGER.start(
            build_bulk_plan(db_path, request_interval=QUIET_REQUEST_INTERVAL, quiet=True)
        )
    except RuntimeError:
        return False  # 使用者剛好自己啟動了下載，讓給使用者
    return True


def _start_quiet_sync_loop(db_path: Path) -> None:
    """背景安靜同步迴圈：只在 main() 啟動（測試直接 import 不受影響）。"""

    def _worker() -> None:
        time.sleep(5.0)  # 先讓 server 與 seed merge 起跑
        while True:
            try:
                _run_quiet_sync_once(db_path)
            except Exception:  # noqa: BLE001 - 背景安全網，任何失敗都不影響 app
                pass
            time.sleep(QUIET_SYNC_LOOP_SECONDS)

    threading.Thread(target=_worker, name="quiet-sync", daemon=True).start()


def _start_seed_merge_if_needed(db_path: Path) -> None:
    if not getattr(sys, "frozen", False):
        return

    def _worker() -> None:
        result = _apply_seed_now(db_path, force=False)
        message = _seed_merge_message(result, manual=False)
        if message:
            print(message)

    threading.Thread(target=_worker, name="seed-merge", daemon=True).start()


def _apply_seed_now(db_path: Path, *, force: bool) -> dict[str, object]:
    with SQLiteStore(db_path) as store:
        return maybe_merge_seed(
            store,
            seed_dir=seed_dir(),
            current_db=db_path,
            app_version=APP_VERSION,
            backups_dir=data_dir() / "backups",
            force=force,
        )


def _seed_merge_message(result: dict[str, object], *, manual: bool) -> str:
    if result.get("applied"):
        rows = int(result.get("rows") or 0)
        version = result.get("version") or "--"
        return f"官方資料包已套用：版本 {version}，新增 {rows} 筆公開資料。你的自選股、持倉與設定不會被覆蓋。"
    reason = str(result.get("reason") or "")
    if not manual and reason in {"missing_manifest", "already_applied"}:
        return ""
    labels = {
        "missing_manifest": "這個版本沒有隨包官方資料包。",
        "invalid_manifest_version": "官方資料包版本資訊不完整，已跳過。",
        "app_too_old": "官方資料包需要更新的程式版本，已跳過。",
        "already_applied": "這份官方資料包已經套用過。",
        "missing_seed_db": "找不到官方資料包資料庫。",
        "sha256_mismatch": "官方資料包驗證失敗，已跳過。",
        "error": "套用官方資料包時發生錯誤，未改動你的資料。",
    }
    detail = labels.get(reason, f"官方資料包未套用：{reason or '未知原因'}。")
    if result.get("error"):
        detail = f"{detail} ({result.get('error')})"
    return detail


def _configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _quote_provider() -> TwseMisQuoteProvider:
    return TwseMisQuoteProvider(TwseClient(timeout=5.0, request_interval=0.0))


def _app_info_payload(db_path: Path = DEFAULT_DB) -> dict[str, object]:
    seed_version = 0
    with SQLiteStore(db_path) as store:
        seed_version = applied_seed_version(store)
    return {
        "version": APP_VERSION,
        "update_source": "GitHub Releases",
        "update_privacy": "只連 GitHub 取得版本號與下載連結，不上傳任何本地資料。",
        "data_snapshot_version": seed_version,
        "bundled_data_snapshot_version": seed_manifest_version(seed_dir()),
        "frozen": bool(getattr(sys, "frozen", False)),
    }


def _latest_update_info(*, force: bool = False) -> dict[str, object]:
    now = time.monotonic()
    cached = _UPDATE_CHECK_CACHE.get("payload")
    checked_at = float(_UPDATE_CHECK_CACHE.get("checked_at") or 0.0)
    if not force and isinstance(cached, dict) and now - checked_at < UPDATE_CHECK_CACHE_SECONDS:
        return dict(cached)

    payload = check_for_update(APP_VERSION)
    payload["checked_at"] = datetime.now().isoformat(timespec="seconds")
    payload["cache_seconds"] = UPDATE_CHECK_CACHE_SECONDS
    _UPDATE_CHECK_CACHE["payload"] = dict(payload)
    _UPDATE_CHECK_CACHE["checked_at"] = now
    return payload


def _legacy_import_paths() -> tuple[Path, Path, Path]:
    current_dir = data_dir()
    legacy_dir = external_root() / "data"
    return (
        legacy_dir / "stock_translator.sqlite3",
        current_dir / "stock_translator.sqlite3",
        legacy_dir,
    )


def _legacy_import_dismissed_path() -> Path:
    return data_dir() / ".legacy_import_dismissed"


def _legacy_import_payload() -> dict[str, object]:
    if not getattr(sys, "frozen", False):
        return {
            "available": False,
            "dismissed": False,
            "legacy_stock_count": 0,
            "current_stock_count": 0,
            "reason": "dev_mode",
        }

    marker = _legacy_import_dismissed_path()
    if marker.is_file():
        return {
            "available": False,
            "dismissed": True,
            "legacy_stock_count": 0,
            "current_stock_count": 0,
        }

    legacy_db, current_db, _legacy_dir = _legacy_import_paths()
    payload = dict(legacy_import_status(legacy_db, current_db))
    payload["dismissed"] = False
    return payload


def _write_legacy_import_dismissed() -> None:
    marker = _legacy_import_dismissed_path()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("", encoding="utf-8")


def _sync_outcome_payload(result: SyncResult) -> dict[str, object]:
    status = _sync_outcome_status(result)
    return {
        "status": status,
        "current": status == "current",
        "needs_retry": status in {"partial", "retry"},
        "user_message": _sync_user_message(result, status),
    }


def _sync_outcome_status(result: SyncResult) -> str:
    coverage_status = str((result.coverage or {}).get("status") or "")
    post_status = str((result.post_status or {}).get("status") or "")
    if coverage_status in {"current", "patched"} or post_status in {"current", "patched"}:
        return "current"
    if result.rows_written > 0:
        return "partial"
    return "retry"


def _sync_user_message(result: SyncResult, status: str) -> str:
    coverage = result.coverage or {}
    gap = result.gap_plan or {}
    latest = coverage.get("latest_date") or gap.get("local_latest_date") or "無資料"
    target = coverage.get("target_date") or gap.get("target_date") or "最近收盤日"
    if status == "current":
        return f"{result.stock_id} 已補到最近收盤 {target}。"

    if result.rows_written > 0:
        if result.price_warning_count:
            return (
                f"{result.stock_id} 有補進 {result.rows_written} 筆，但日線仍停在 {latest}，"
                f"還沒到 {target}。剛剛有 {result.price_warning_count} 個月份抓取失敗，"
                "通常是證交所限流或連線中斷；請等 1-2 分鐘再按一次補這檔。"
            )
        return (
            f"{result.stock_id} 有補進 {result.rows_written} 筆，但日線仍停在 {latest}，"
            f"還沒到 {target}。可能是資料源尚未公布或局部月份缺資料；請稍後再試一次。"
        )

    return (
        f"{result.stock_id} 這次沒有抓到新的日線資料，目前最後是 {latest}，目標是 {target}。"
        "可能是證交所暫時沒回應、正在限流，或該檔當天尚未公布；請稍後再試一次。"
    )


def _date_or_none(value: object) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _bulk_status(db_path: Path) -> dict[str, object]:
    status = BULK_MANAGER.status()
    with SQLiteStore(db_path) as store:
        persisted = store.get_bulk_progress_summary(BULK_RUN_KEY)
    status["persisted"] = persisted
    persisted_counts = persisted.get("counts") if isinstance(persisted.get("counts"), dict) else {}
    source_pending_count = int(persisted_counts.get("source_pending", 0)) if persisted_counts else 0
    history_pending_count = int(persisted_counts.get("history_pending", 0)) if persisted_counts else 0
    status["source_pending_count"] = source_pending_count
    status["history_pending_count"] = history_pending_count
    status["can_retry_failed"] = bool(persisted.get("failed_count")) and not bool(status.get("running"))

    if not status.get("running") and status.get("status") == "idle" and persisted.get("total"):
        total = int(persisted.get("total") or 0)
        done = int(persisted.get("done") or 0)
        failed_count = int(persisted.get("failed_count") or 0)
        status.update(
            {
                "status": "done" if done >= total and failed_count == 0 else "paused",
                "total": total,
                "done": done,
                "failed": persisted.get("failed", []),
                "failed_count": failed_count,
                "source_pending_count": source_pending_count,
                "history_pending_count": history_pending_count,
                "message": "讀到上次下載進度；按開始下載會接續，或只重試失敗清單。",
                "running": False,
                "paused": False,
                "current": None,
            }
        )
    elif persisted.get("failed_count") and not status.get("failed_count"):
        status["failed"] = persisted.get("failed", [])
        status["failed_count"] = persisted.get("failed_count", 0)

    return status


def _bulk_blocks_twse_fetch(path: str, status: dict[str, object] | None = None) -> bool:
    if path not in TWSE_FETCH_BLOCKED_DURING_BULK:
        return False
    current = status if status is not None else BULK_MANAGER.status()
    if current.get("mode") == "quiet":
        # 背景安靜補歷史不鎖使用者操作（間隔慢，與使用者請求並行無虞）。
        return False
    return bool(
        current.get("running")
        or current.get("paused")
        or current.get("status") in {"preparing", "running", "paused"}
    )


def _report_news_payload(stock_id: str, short_name: str) -> dict[str, object]:
    try:
        return fetch_company_news(stock_id, short_name, days=14, limit=8, timeout=3.0)
    except Exception as exc:  # noqa: BLE001 - report export should degrade, not fail
        return {
            "status": "unavailable",
            "stock_id": stock_id,
            "name": short_name,
            "days": 14,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "overall": f"目前無法取得新聞（{exc}），報告先保留已同步資料。",
            "overall_label": "無消息",
            "counts": {"利多": 0, "利空": 0, "中性": 0},
            "top": [],
            "items": [],
            "risk_summary": {
                "score": 0,
                "level": "無",
                "top_dimensions": [],
                "reasons": [],
                "windows": {"d7": 0, "d14": 0, "d45": 0},
                "heating": False,
            },
            "sources": {},
            "disclaimer": "消息整理為多來源公開新聞的關鍵字歸類，僅供快速了解，非投資建議、不預測股價。",
        }


if __name__ == "__main__":
    raise SystemExit(main())
