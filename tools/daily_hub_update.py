"""把「當日增量」套進官方資料包 baseline DB（GitHub Actions 每日發布用）。

設計原則（見 docs/00-AGENT必讀 與 docs/18）：
- 只做便宜的全市場整批請求（每天約 6~9 個 API 呼叫），絕不逐檔抓 STOCK_DAY 歷史。
  歷史 baseline 來自初始資料包；受益證券/ETN 等個股歷史端點不提供的商品，
  就是靠這裡的 STOCK_DAY_ALL top-up 天天累積，代替每台使用者電腦各自爬。
- 冪等：同一天重跑（第二班次）時日線沒有前進 → publish=no，workflow 跳過發布。
- 單項加值資料失敗只記 warning，不擋整包；openapi 主資料失敗才算致命。

輸出 GITHUB_OUTPUT 格式：
  publish=yes|no
  summary=...（人話摘要）
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.analyze.dividends import dedupe_dividend_records
from app.analyze.twse_calendar import is_twse_trading_day
from app.store.sqlite_store import SQLiteStore
from app.sync.twse import TwseClient

T86_LOOKBACK_TRADING_DAYS = 10  # 補近 N 個交易日缺的法人資料（涵蓋週末＋短假期）


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply today's incremental TWSE data onto a hub baseline DB.")
    parser.add_argument("--db", type=Path, required=True, help="baseline 資料庫（解壓自上一版官方資料包）")
    parser.add_argument("--skip-t86", action="store_true", help="T86 端點不可達時跳過法人補抓")
    parser.add_argument(
        "--request-interval",
        type=float,
        default=1.0,
        help="TWSE 請求間隔秒數（官方發布端不趕時間，預設溫和的 1.0）",
    )
    args = parser.parse_args()

    db_path = args.db.resolve()
    if not db_path.is_file():
        print("publish=no")
        print(f"summary=baseline DB 不存在：{db_path}")
        return 2

    taipei_today = datetime.now(ZoneInfo("Asia/Taipei")).date()
    warnings: list[str] = []

    with SQLiteStore(db_path) as store:
        client = TwseClient(request_interval=args.request_interval)

        before_latest = _max_daily_date(store)

        # 1) 上市清單（openapi；失敗 = 主來源不可用，致命）
        try:
            profiles = client.fetch_listed_profiles()
            store.upsert_profiles(profiles)
        except Exception as exc:  # noqa: BLE001
            print("publish=no")
            print(f"summary=上市清單抓取失敗（{str(exc)[:120]}），視為 openapi 不可用，今天不發布。")
            return 2

        # 2) 全市場最新收盤（openapi；資料包的每日核心）
        try:
            latest_all = client.fetch_latest_all_prices()
            if latest_all:
                store.upsert_daily_prices(latest_all)
        except Exception as exc:  # noqa: BLE001
            print("publish=no")
            print(f"summary=STOCK_DAY_ALL 抓取失敗（{str(exc)[:120]}），今天不發布。")
            return 2

        after_latest = _max_daily_date(store)
        if after_latest is None or (before_latest is not None and after_latest <= before_latest):
            # 日線沒有前進：來源尚未更新（第一班次太早）或今天已發過（第二班次）。
            print("publish=no")
            print(
                "summary=日線最新日未前進"
                f"（{before_latest} → {after_latest}），來源尚未更新或本日已發布，跳過。"
            )
            return 0

        # 3) 三大法人 T86（rwd 端點；只補近 N 個交易日缺的日期）
        t86_days_written = 0
        if not args.skip_t86:
            have = store.get_institutional_dates_any()
            day = taipei_today
            checked = 0
            while checked < T86_LOOKBACK_TRADING_DAYS:
                if is_twse_trading_day(day):
                    checked += 1
                    if day.isoformat() not in have:
                        try:
                            trades = client.fetch_institutional_trades_for_date(day)
                        except Exception as exc:  # noqa: BLE001
                            warnings.append(f"T86 {day.isoformat()} 失敗：{str(exc)[:80]}")
                            break  # rwd 被擋多半整段都不通，別逐日撞
                        if trades:
                            store.upsert_institutional_trades(trades)
                            t86_days_written += 1
                day -= timedelta(days=1)

        # 4) 全市場加值資料（openapi；單項失敗不擋整包）
        shared_rows: dict[str, int] = {}
        for label, fetch, save in (
            ("月營收", client.fetch_all_monthly_revenues, store.upsert_monthly_revenues),
            ("估值", client.fetch_all_market_valuations, store.upsert_market_valuations),
            ("財報", client.fetch_all_financial_statements, store.upsert_financial_statements),
        ):
            try:
                shared_rows[label] = int(save(fetch()) or 0)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"{label} 失敗：{str(exc)[:80]}")

        # 5) 股利：公告口徑（openapi）＋今年除權息結果（TWT49U，rwd）
        try:
            records = client.fetch_all_dividend_records()
            try:
                year_start = taipei_today.replace(month=1, day=1)
                records.extend(
                    client.fetch_all_historical_dividend_records(year_start, taipei_today)
                )
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"除權息歷史失敗：{str(exc)[:80]}")
            shared_rows["股利"] = int(
                store.upsert_dividend_records(dedupe_dividend_records(records)) or 0
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"股利失敗：{str(exc)[:80]}")

    shared_text = "、".join(f"{label} {rows}" for label, rows in shared_rows.items()) or "無"
    warn_text = f"；警告：{'；'.join(warnings)}" if warnings else ""
    print("publish=yes")
    print(
        f"summary=日線推進到 {after_latest}；T86 補 {t86_days_written} 個交易日；"
        f"加值資料（{shared_text}）{warn_text}"
    )
    return 0


def _max_daily_date(store: SQLiteStore) -> str | None:
    row = store.conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()
    value = row[0] if row else None
    return str(value) if value else None


if __name__ == "__main__":
    raise SystemExit(main())
