"""下載並驗證 GitHub 最新官方資料，作為 release build 的唯一資料來源。

發行包不得再從開發機 LOCALAPPDATA 打包；否則 manifest 日期看似最新，內容卻可能
停在數週前。這裡會驗 SHA-256、SQLite、最新日與上櫃歷史深度，任一不合格就擋 build。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.update.data_hub import check_for_data_hub, prepare_data_hub

DEFAULT_OUTPUT_DIR = ROOT / "dist" / "official_data"


def main() -> int:
    _configure_output()
    parser = argparse.ArgumentParser(
        description="Prepare verified official data for an app release."
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-stale-days", type=int, default=7)
    parser.add_argument("--min-tpex-deep-stocks", type=int, default=700)
    parser.add_argument("--min-tpex-rows", type=int, default=120)
    args = parser.parse_args()

    info = check_for_data_hub(0, include_current=True)
    if not info.get("available"):
        raise SystemExit(str(info.get("message") or "GitHub 沒有可用的官方資料包。"))
    prepared = prepare_data_hub(info)
    stats = validate_release_data(
        prepared.hub_dir,
        max_stale_days=max(0, args.max_stale_days),
        min_tpex_deep_stocks=max(0, args.min_tpex_deep_stocks),
        min_tpex_rows=max(1, args.min_tpex_rows),
    )

    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        shutil.rmtree(output_dir)
    shutil.copytree(prepared.hub_dir, output_dir)
    print(f"Official data snapshot: {stats['snapshot_version']}")
    print(f"Latest daily price: {stats['latest_date']}")
    print(
        f"TPEX history: {stats['deep_tpex_stocks']} / {stats['tpex_stocks']} stocks "
        f"have at least {args.min_tpex_rows} rows"
    )
    print(f"Prepared: {output_dir}")
    return 0


def validate_release_data(
    hub_dir: Path,
    *,
    max_stale_days: int,
    min_tpex_deep_stocks: int,
    min_tpex_rows: int,
    today: date | None = None,
) -> dict[str, object]:
    manifest_path = hub_dir / "manifest.json"
    db_path = hub_dir / "data" / "stock_translator.sqlite3"
    if not manifest_path.is_file() or not db_path.is_file():
        raise ValueError("官方資料包缺少 manifest.json 或 SQLite 資料庫。")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshot_version = int(manifest.get("data_snapshot_version") or 0)
    if snapshot_version <= 0:
        raise ValueError("官方資料包缺少有效資料版本。")

    conn = sqlite3.connect(str(db_path))
    try:
        quick_check = str(conn.execute("PRAGMA quick_check").fetchone()[0])
        if quick_check.lower() != "ok":
            raise ValueError(f"官方 SQLite quick_check 失敗：{quick_check}")
        row = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()
        latest_text = str(row[0] or "") if row else ""
        latest_date = date.fromisoformat(latest_text) if latest_text else None
        if latest_date is None:
            raise ValueError("官方資料包沒有任何日線資料。")
        cutoff = (today or date.today()) - timedelta(days=max_stale_days)
        if latest_date < cutoff:
            raise ValueError(
                f"官方資料包太舊：最後日線 {latest_date.isoformat()}，最低要求 {cutoff.isoformat()}。"
            )
        tpex_stocks = int(
            conn.execute(
                "SELECT COUNT(*) FROM stock_profiles WHERE UPPER(market) = 'TPEX'"
            ).fetchone()[0]
        )
        deep_tpex_stocks = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT p.stock_id
                    FROM stock_profiles AS p
                    JOIN daily_prices AS d ON d.stock_id = p.stock_id
                    WHERE UPPER(p.market) = 'TPEX'
                    GROUP BY p.stock_id
                    HAVING COUNT(*) >= ?
                )
                """,
                (min_tpex_rows,),
            ).fetchone()[0]
        )
    finally:
        conn.close()

    if deep_tpex_stocks < min_tpex_deep_stocks:
        raise ValueError(
            "上櫃歷史 baseline 不完整："
            f"只有 {deep_tpex_stocks}/{tpex_stocks} 檔達 {min_tpex_rows} 筆，"
            f"最低要求 {min_tpex_deep_stocks} 檔。"
        )
    return {
        "snapshot_version": snapshot_version,
        "latest_date": latest_date.isoformat(),
        "tpex_stocks": tpex_stocks,
        "deep_tpex_stocks": deep_tpex_stocks,
    }


def _configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    raise SystemExit(main())
