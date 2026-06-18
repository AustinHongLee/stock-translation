from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from app.screener.value import DEFAULT_SCREENER_PATH, refresh_value_screener
from app.store.sqlite_store import SQLiteStore
from app.sync.service import StockSyncService
from app.sync.twse import TwseClient

DEFAULT_DB = Path("data/stock_translator.sqlite3")


def main(argv: list[str] | None = None) -> int:
    _configure_output()
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-db":
        with SQLiteStore(args.db):
            pass
        print(f"Initialized database: {args.db}")
        return 0

    if args.command == "sync-stock":
        with SQLiteStore(args.db) as store:
            service = StockSyncService(
                client=TwseClient(request_interval=args.request_interval),
                store=store,
            )
            result = service.sync_stock_history(
                args.stock_id,
                lookback_days=args.lookback_days,
                end_date=args.end_date,
            )
            profile = store.get_profile(args.stock_id)
            label = f"{profile.short_name} " if profile else ""
            print(f"{args.stock_id} {label}{result.message}")
        return 0

    if args.command == "show-stock":
        with SQLiteStore(args.db) as store:
            profile = store.get_profile(args.stock_id)
            prices = store.get_daily_prices(args.stock_id, limit=args.limit)
        if profile:
            print(f"{profile.stock_id} {profile.short_name} ({profile.name})")
        else:
            print(args.stock_id)
        if not prices:
            print("No local prices. Run sync-stock first.")
            return 1
        print("date        open      high      low       close     volume")
        for item in prices:
            print(
                f"{item.date.isoformat()}  "
                f"{item.open:8.2f}  {item.high:8.2f}  {item.low:8.2f}  "
                f"{item.close:8.2f}  {item.volume:>10}"
            )
        return 0

    if args.command == "search":
        with SQLiteStore(args.db) as store:
            results = store.search_profiles(args.query, limit=args.limit)
        if not results:
            print("No local profiles. Run sync-stock for a known stock first.")
            return 1
        for item in results:
            print(f"{item.stock_id}\t{item.short_name}\t{item.name}")
        return 0

    if args.command == "refresh-screener":
        result = refresh_value_screener(
            TwseClient(request_interval=args.request_interval),
            output_path=args.output,
            dividend_years=args.dividend_years,
            fetch_years=args.fetch_years,
        )
        print(
            f"Updated value screener: {result.rows} rows -> {result.output_path} "
            f"({result.source_start_date} to {result.source_end_date})"
        )
        if result.warnings:
            print(f"Warnings: {len(result.warnings)}; first: {result.warnings[0]}")
        return 0

    parser.print_help()
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Stock translator local data CLI.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help=f"SQLite database path. Default: {DEFAULT_DB}",
    )

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init-db", help="Create the local SQLite schema.")

    sync_parser = subparsers.add_parser(
        "sync-stock",
        help="Fetch one TWSE stock history into the local database.",
    )
    sync_parser.add_argument("stock_id", help="TWSE stock id, for example 2330.")
    sync_parser.add_argument(
        "--lookback-days",
        type=int,
        default=365,
        help="How many days of history to fetch. Default: 365.",
    )
    sync_parser.add_argument(
        "--end-date",
        type=date.fromisoformat,
        default=None,
        help="Inclusive end date in YYYY-MM-DD. Default: today.",
    )
    sync_parser.add_argument(
        "--request-interval",
        type=float,
        default=0.2,
        help="Seconds to wait between monthly TWSE requests. Default: 0.2.",
    )

    show_parser = subparsers.add_parser(
        "show-stock",
        help="Show local daily prices for one stock.",
    )
    show_parser.add_argument("stock_id", help="TWSE stock id, for example 2330.")
    show_parser.add_argument("--limit", type=int, default=10)

    search_parser = subparsers.add_parser(
        "search",
        help="Search local stock profiles by id or name.",
    )
    search_parser.add_argument("query")
    search_parser.add_argument("--limit", type=int, default=20)

    screener_parser = subparsers.add_parser(
        "refresh-screener",
        help="Refresh the all-market low-price value screener without per-stock sync.",
    )
    screener_parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_SCREENER_PATH,
        help=f"Output JSON path. Default: {DEFAULT_SCREENER_PATH}",
    )
    screener_parser.add_argument(
        "--dividend-years",
        type=int,
        default=5,
        help="How many recent dividend years to average. Default: 5.",
    )
    screener_parser.add_argument(
        "--fetch-years",
        type=int,
        default=6,
        help="How many calendar years of ex-dividend history to fetch. Default: 6.",
    )
    screener_parser.add_argument(
        "--request-interval",
        type=float,
        default=0.2,
        help="Seconds to wait between annual TWSE requests. Default: 0.2.",
    )

    return parser


def _configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    raise SystemExit(main())
