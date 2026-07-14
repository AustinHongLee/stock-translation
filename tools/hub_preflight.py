"""Data Hub 每日自動發布的 preflight：交易日判斷＋TWSE 連通性。

在 GitHub Actions 上執行，輸出 GITHUB_OUTPUT 格式的 key=value：
  proceed=yes|no   今天要不要跑（非交易日或 openapi 不通 → no）
  reason=...       人話原因（寫進 step summary）
  t86=yes|no       T86（www.twse.com.tw/rwd）可達性；不可達時仍可發「top-up only」包

設 FORCE_RUN=1 可跳過交易日檢查（workflow_dispatch 手動補跑用）。
openapi 不通視為「今天不發」而不是整個 job 失敗——海外 runner 偶發被擋時
不要每天寄失敗信；連續多天 no 才需要人工看 summary。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.analyze.twse_calendar import is_twse_trading_day

OPENAPI_PROBE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
T86_PROBE_URL = (
    "https://www.twse.com.tw/rwd/zh/fund/T86?date={date}&selectType=ALLBUT0999&response=json"
)
USER_AGENT = "stock-translator-data-hub/1.0 (+github actions daily publisher)"


def _probe(url: str, *, timeout: float = 20.0) -> tuple[bool, str]:
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8-sig"))
    except Exception as exc:  # noqa: BLE001 - preflight 只分可達/不可達
        return False, str(exc)
    if isinstance(payload, (list, dict)):
        return True, "ok"
    return False, "unexpected payload type"


def main() -> int:
    taipei_today = datetime.now(ZoneInfo("Asia/Taipei")).date()
    force = bool(os.environ.get("FORCE_RUN", "").strip())

    if not force and not is_twse_trading_day(taipei_today):
        print("proceed=no")
        print(f"reason=台北 {taipei_today.isoformat()} 非交易日，不需發布。")
        print("t86=no")
        return 0

    openapi_ok, openapi_msg = _probe(OPENAPI_PROBE_URL)
    if not openapi_ok:
        print("proceed=no")
        print(f"reason=TWSE openapi 不可達（{openapi_msg[:120]}），今天略過；連續發生請檢查 runner 出口 IP 是否被擋。")
        print("t86=no")
        return 0

    t86_ok, t86_msg = _probe(T86_PROBE_URL.format(date=taipei_today.strftime("%Y%m%d")))
    print("proceed=yes")
    if t86_ok:
        print(f"reason=台北 {taipei_today.isoformat()} 為交易日，openapi 與 T86 皆可達。")
        print("t86=yes")
    else:
        print(f"reason=台北 {taipei_today.isoformat()} 為交易日；openapi 可達、T86 不可達（{t86_msg[:120]}），法人資料留給客戶端自行補。")
        print("t86=no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
