"""Relationship layer: cross-source confirmation plus readability filter.

This module only reshapes facts already present in the stock payload.  It does
not fetch data, score direction, or recalculate base indicators such as RSI,
MACD, or moving averages.
"""
from __future__ import annotations

import math
from typing import Any


DISCLAIMER = "資料關係描述：只整理目前資料彼此是否同向，非投資建議。"
FORBIDDEN_CONFIRM = "扎實只描述價、量與大戶資料同不同步，不等於後續走勢承諾。"
FORBIDDEN_READABILITY = "可信度只表示這段資料好不好閱讀，不代表方向。"
FORBIDDEN_DERIVATION = "這只是算法來源說明，不含方向判斷。"
FORBIDDEN_PROGRESSION = "階段描述只整理目前形狀，不是變化承諾。"
FORBIDDEN_CONTEXT = "背景資料只輔助理解，不當成操作理由。"


def build_relationships_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Build relationship items from an already assembled stock payload."""
    data = payload if isinstance(payload, dict) else {}
    prices = _valid_prices(data.get("prices"))
    features = _dict(data.get("features"))
    readability = relationship_readability(_dict(data.get("structure")))
    items: list[dict[str, Any]] = []

    for window in (1, 5):
        item = _cross_source_confirmation(data, prices, features, readability, window=window)
        if item:
            items.append(item)

    for builder in (_derivation_macd, _derivation_bollinger, _derivation_kd, _progression_ma, _progression_bollinger, _fundamental_context):
        item = builder(data, prices, features, readability)
        if item:
            items.append(item)

    return {
        "available": bool(items),
        "as_of_date": prices[-1]["date"] if prices else None,
        "readability": readability,
        "items": items,
        "disclaimer": DISCLAIMER,
    }


def relationship_readability(structure: dict[str, Any] | None) -> dict[str, str]:
    """Turn structure fingerprint dimensions into a reading reliability label."""
    data = _dict(structure)
    if not data.get("available"):
        return {
            "level": "medium",
            "plain": "結構資料還不完整，下面的判讀先保守閱讀。",
            "why": "性格層資料不足時，不把事件層解讀說得太滿。",
            "forbidden": FORBIDDEN_READABILITY,
        }
    dims = {str(item.get("key")): item for item in data.get("dimensions") or [] if isinstance(item, dict)}
    complexity = _level(dims.get("complexity"))
    turbulence = _level(dims.get("turbulence"))
    chroma = _level(dims.get("chroma"))
    memory = _level(dims.get("memory"))

    if complexity >= 4 or turbulence >= 4 or (chroma > 0 and chroma <= 1):
        level = "low"
        plain = "這檔最近很亂，下面的判讀參考就好。"
        why = "複雜度、湍流或噪音色偏亂時，價量與籌碼的關係容易反覆。"
    elif memory >= 4 and complexity <= 3 and turbulence <= 3:
        level = "high"
        plain = "這檔最近蠻好讀，判讀比較可信。"
        why = "延續性較高且亂度沒有明顯偏高時，事件層資料比較容易對齊。"
    else:
        level = "medium"
        plain = "這檔最近可讀性普通，判讀要留一點折扣。"
        why = "性格層沒有明顯單一特徵，事件層仍要和其他資料交叉閱讀。"
    return {"level": level, "plain": plain, "why": why, "forbidden": FORBIDDEN_READABILITY}


def _cross_source_confirmation(
    payload: dict[str, Any],
    prices: list[dict[str, Any]],
    features: dict[str, Any],
    readability: dict[str, str],
    *,
    window: int,
) -> dict[str, Any] | None:
    if len(prices) <= window:
        return None
    start = prices[-window - 1]["close"]
    end = prices[-1]["close"]
    if start <= 0:
        return None
    change_pct = (end - start) / start * 100
    price_dir = _direction(change_pct)
    if price_dir == "flat":
        return _relationship_item(
            key=f"confirm_{window}d",
            group="confirm",
            label=f"近 {window} 日漲跌扎不扎實",
            plain="這段價格變化不大，先看成整理。",
            why="跨源確認會先看價格是否真的有明顯變動，變化太小時不硬解讀。",
            detail=f"{window} 日報酬 {_fmt_pct(change_pct)}；價格方向：整理。",
            forbidden=FORBIDDEN_CONFIRM,
            reliability=readability["level"],
            targets=_window_targets(prices, window),
        )

    volume = _volume_state(features, window)
    inst = _institutional_state(payload, window)
    agreement_sources: list[tuple[str, bool]] = []
    volume_agrees = bool(volume["usable"] and volume["state"] == "strong")
    inst_agrees = bool(
        inst["usable"]
        and ((price_dir == "up" and inst["state"] == "inflow") or (price_dir == "down" and inst["state"] == "outflow"))
    )
    if volume["usable"]:
        agreement_sources.append(("volume", volume_agrees))
    if inst["usable"]:
        agreement_sources.append(("institutional", inst_agrees))
    agree = sum(1 for _, ok in agreement_sources if ok)
    total = len(agreement_sources)
    plain = _confirm_plain(price_dir, volume, inst, agree, total)
    detail = (
        f"{window} 日報酬 {_fmt_pct(change_pct)}；"
        f"量能：{volume['detail']}；"
        f"大戶資料：{inst['detail']}；"
        f"同向來源 {agree}/{total}。"
    )
    return _relationship_item(
        key=f"confirm_{window}d",
        group="confirm",
        label=f"近 {window} 日漲跌扎不扎實",
        plain=plain,
        why="老手會把價格、成交量和大戶資料放在一起看，確認這次變動是不是多個來源同時指向同一邊。",
        detail=detail,
        forbidden=FORBIDDEN_CONFIRM,
        reliability=readability["level"],
        targets=_window_targets(prices, window),
    )


def _derivation_macd(payload: dict[str, Any], prices: list[dict[str, Any]], features: dict[str, Any], readability: dict[str, str]) -> dict[str, Any] | None:
    latest = _dict(features.get("latest"))
    if _number(latest.get("macd")) is None:
        return None
    return _relationship_item(
        key="derivation_macd",
        group="derivation",
        label="MACD 來源關係",
        plain="這條副圖其實是兩條平均線拉開的距離。",
        why="把來源線和副圖連起來看，能知道它不是神秘訊號，而是均線距離的整理。",
        detail=f"MACD DIF {_fmt(latest.get('macd'))}；Signal {_fmt(latest.get('macd_signal'))}；柱 {_fmt(latest.get('macd_histogram'))}。",
        forbidden=FORBIDDEN_DERIVATION,
        reliability=readability["level"],
        targets=[{"type": "ma", "key": "ema12"}, {"type": "ma", "key": "ema26"}, {"type": "subplot", "key": "macd"}],
    )


def _derivation_bollinger(payload: dict[str, Any], prices: list[dict[str, Any]], features: dict[str, Any], readability: dict[str, str]) -> dict[str, Any] | None:
    latest = _dict(features.get("latest"))
    if _number(latest.get("bb_upper")) is None or _number(latest.get("bb_lower")) is None:
        return None
    return _relationship_item(
        key="derivation_bollinger",
        group="derivation",
        label="布林通道來源關係",
        plain="這個通道是平均線加上波動範圍。",
        why="布林通道把中線和波動寬度放在一起，幫助看目前價格在通道中的位置。",
        detail=f"布林位置 {_fmt_pct(latest.get('bb_position'))}；布林寬度 {_fmt_pct(latest.get('bb_width'))}。",
        forbidden=FORBIDDEN_DERIVATION,
        reliability=readability["level"],
        targets=[{"type": "ma", "key": "bb_upper"}, {"type": "ma", "key": "bb_middle"}, {"type": "ma", "key": "bb_lower"}],
    )


def _derivation_kd(payload: dict[str, Any], prices: list[dict[str, Any]], features: dict[str, Any], readability: dict[str, str]) -> dict[str, Any] | None:
    latest = _dict(features.get("latest"))
    if _number(latest.get("kd_k")) is None or _number(latest.get("kd_d")) is None:
        return None
    return _relationship_item(
        key="derivation_kd",
        group="derivation",
        label="KD 來源關係",
        plain="這個副圖在看收盤落在近期高低範圍的哪裡。",
        why="把 KD 還原成高低區間位置，比單看高低檔更不容易誤讀。",
        detail=f"K {_fmt(latest.get('kd_k'))}；D {_fmt(latest.get('kd_d'))}。",
        forbidden=FORBIDDEN_DERIVATION,
        reliability=readability["level"],
        targets=[{"type": "subplot", "key": "kd"}],
    )


def _progression_ma(payload: dict[str, Any], prices: list[dict[str, Any]], features: dict[str, Any], readability: dict[str, str]) -> dict[str, Any] | None:
    latest = _dict(features.get("latest"))
    ma_values = [_number(latest.get(key)) for key in ("ma5", "ma20", "ma60")]
    if any(value is None for value in ma_values):
        return None
    close = prices[-1]["close"] if prices else None
    spread = _ma_spread([float(value) for value in ma_values if value is not None], close)
    if spread is None:
        return None
    if spread <= 2.2:
        plain = "三條平均線現在黏在一起，圖形還在整理。"
        stage = "糾結"
    elif spread >= 6:
        plain = "三條平均線已經散開，圖形方向比較集中。"
        stage = "發散"
    else:
        plain = "三條平均線有點距離，但還沒有拉得很開。"
        stage = "過渡"
    return _relationship_item(
        key="progression_ma_spread",
        group="progression",
        label="均線糾結到發散",
        plain=plain,
        why="均線從黏合到散開，是把價格整理程度轉成階段感的方式。",
        detail=f"MA5/20/60 離散約 {_fmt_pct(spread)}；目前階段：{stage}。",
        forbidden=FORBIDDEN_PROGRESSION,
        reliability=readability["level"],
        targets=[{"type": "ma", "key": "ma5"}, {"type": "ma", "key": "ma20"}, {"type": "ma", "key": "ma60"}],
    )


def _progression_bollinger(payload: dict[str, Any], prices: list[dict[str, Any]], features: dict[str, Any], readability: dict[str, str]) -> dict[str, Any] | None:
    latest = _dict(features.get("latest"))
    width = _number(latest.get("bb_width"))
    if width is None:
        return None
    if latest.get("bb_squeeze") is True:
        plain = "通道現在偏窄，價格被收在比較小的範圍裡。"
        stage = "收斂"
    elif width >= 12:
        plain = "通道現在偏寬，最近震盪範圍比較大。"
        stage = "擴張"
    else:
        plain = "通道寬度普通，先當一般波動閱讀。"
        stage = "一般"
    return _relationship_item(
        key="progression_bollinger_width",
        group="progression",
        label="布林收斂到擴張",
        plain=plain,
        why="通道寬窄可以把波動階段視覺化，幫忙看目前價格是被收窄還是震盪變大。",
        detail=f"布林寬度 {_fmt_pct(width)}；目前階段：{stage}。",
        forbidden=FORBIDDEN_PROGRESSION,
        reliability=readability["level"],
        targets=[{"type": "ma", "key": "bb_upper"}, {"type": "ma", "key": "bb_middle"}, {"type": "ma", "key": "bb_lower"}],
    )


def _fundamental_context(payload: dict[str, Any], prices: list[dict[str, Any]], features: dict[str, Any], readability: dict[str, str]) -> dict[str, Any] | None:
    revenue = _dict(payload.get("revenue_summary"))
    financial = _dict(payload.get("financial_summary"))
    if not revenue.get("available") and not financial.get("available"):
        return None
    details = []
    if revenue.get("available"):
        yoy = _fact_value(revenue, "年增率")
        details.append(f"月營收年增 {_fmt_pct(yoy)}" if _number(yoy) is not None else "月營收已同步")
    if financial.get("available"):
        eps = _fact_value(financial, "EPS")
        details.append(f"EPS {_fmt(eps)}" if _number(eps) is not None else "財報已同步")
    return _relationship_item(
        key="fundamental_context",
        group="fundamental_ctx",
        label="低頻背景",
        plain="公司背景資料可以放在旁邊一起看。",
        why="營收與獲利更新比較慢，但能幫忙理解圖形背後是否有基本資料背景。",
        detail="；".join(details) + "。",
        forbidden=FORBIDDEN_CONTEXT,
        reliability="medium",
        targets=[],
    )


def _relationship_item(
    *,
    key: str,
    group: str,
    label: str,
    plain: str,
    why: str,
    detail: str,
    forbidden: str,
    reliability: str,
    targets: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "key": key,
        "group": group,
        "label": label,
        "narration": {"plain": plain, "why": why, "detail": detail},
        "forbidden": forbidden,
        "reliability": reliability if reliability in {"high", "medium", "low"} else "medium",
        "targets": targets,
    }


def _volume_state(features: dict[str, Any], window: int) -> dict[str, Any]:
    series = _dict(features.get("series"))
    ratios = _recent_numbers(series.get("volume_ratio"), window)
    if ratios:
        ratio = sum(ratios) / len(ratios)
    else:
        ratio = _number(_dict(features.get("latest")).get("volume_ratio"))
    if ratio is None:
        return {"usable": False, "agrees": False, "state": "missing", "detail": "無資料"}
    if ratio >= 1.2:
        state = "strong"
        detail = f"量增（約 {_fmt(ratio)} 倍）"
    elif ratio <= 0.8:
        state = "dry"
        detail = f"量縮（約 {_fmt(ratio)} 倍）"
    else:
        state = "normal"
        detail = f"正常（約 {_fmt(ratio)} 倍）"
    return {"usable": state != "normal", "agrees": state == "strong", "state": state, "detail": detail}


def _institutional_state(payload: dict[str, Any], window: int) -> dict[str, Any]:
    rows = [item for item in payload.get("chips_series") or [] if isinstance(item, dict)]
    if not rows:
        return {"usable": False, "agrees": False, "state": "missing", "detail": "無資料"}
    recent = rows[-window:]
    total = sum(_number(item.get("total_net")) or 0 for item in recent)
    if total > 0:
        state = "inflow"
        detail = f"合計流入 {_fmt_lots(total)}"
    elif total < 0:
        state = "outflow"
        detail = f"合計流出 {_fmt_lots(abs(total))}"
    else:
        state = "flat"
        detail = "方向不明"
    return {"usable": state != "flat", "agrees": state == "inflow", "state": state, "detail": detail, "total": total}


def _confirm_plain(price_dir: str, volume: dict[str, Any], inst: dict[str, Any], agree: int, total: int) -> str:
    up = price_dir == "up"
    move = "上漲" if up else "下跌"
    volume_agrees = volume.get("usable") and volume.get("agrees")
    inst_agrees = inst.get("usable") and ((up and inst.get("state") == "inflow") or (not up and inst.get("state") == "outflow"))
    if total == 0:
        return f"這次{move}缺少其他來源確認，先保守看。"
    if volume_agrees and inst_agrees:
        return f"這次{move}有量、大戶也同步，比較扎實。"
    if volume.get("state") == "dry":
        return f"這次{move}量不多，扎實度比較弱。"
    if inst.get("usable") and not inst_agrees:
        return f"這次{move}大戶沒有同步，扎實度要打折。"
    if agree == total:
        return f"這次{move}有其他來源同步，比較扎實。"
    return f"這次{move}資料沒有完全對上，先打折閱讀。"


def _window_targets(prices: list[dict[str, Any]], window: int) -> list[dict[str, Any]]:
    dates = [str(item.get("date")) for item in prices[-window:] if item.get("date")]
    return [{"type": "candles", "dates": dates}, {"type": "subplot", "key": "volume"}]


def _valid_prices(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        close = _number(item.get("close"))
        volume = _number(item.get("volume"))
        if close is None or close <= 0:
            continue
        rows.append({**item, "close": close, "volume": volume})
    return rows


def _recent_numbers(values: Any, count: int) -> list[float]:
    if not isinstance(values, list):
        return []
    out: list[float] = []
    for value in values[-count:]:
        number = _number(value)
        if number is not None:
            out.append(number)
    return out


def _direction(value: float) -> str:
    if value > 0.15:
        return "up"
    if value < -0.15:
        return "down"
    return "flat"


def _ma_spread(values: list[float], close: float | None) -> float | None:
    if not values or close is None or close <= 0:
        return None
    return (max(values) - min(values)) / close * 100


def _level(item: dict[str, Any] | None) -> int:
    value = _number(_dict(item).get("bar_level"))
    return int(value or 0)


def _fact_value(payload: dict[str, Any], label: str) -> Any:
    for fact in payload.get("facts") or []:
        if isinstance(fact, dict) and fact.get("label") == label:
            return fact.get("value")
    return None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _fmt(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "--"
    return f"{number:,.2f}".rstrip("0").rstrip(".")


def _fmt_pct(value: Any) -> str:
    number = _number(value)
    return "--" if number is None else f"{number:+.1f}%"


def _fmt_lots(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "--"
    return f"{number:,.0f} 股"
