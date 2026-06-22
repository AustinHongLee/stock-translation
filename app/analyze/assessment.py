"""體質總評：多因子規則式研究（純函數、可單元測試、不接 AI）。

把價、量、均線、動能指標（RSI／KD）、乖離、位階、籌碼、估值位階、基本面整理成
一張「目前體質」總評卡：每個因子給『目前讀數（事實）＋傳統上偏多／偏空／中性的解讀
＋教學』，最後做中性總結。

紅線：所有輸出只描述現況與『傳統技術分析怎麼看』，**不宣稱未來漲跌方向、不報明牌、不給買賣建議**；市場常常不照技術面走，總結一律附免責，
用詞也避免對價格做出價值高低的斷語。
"""
from __future__ import annotations

import math
from typing import Any, Sequence

LEAN_BULL = "偏多解讀"
LEAN_BEAR = "偏空解讀"
LEAN_NEUTRAL = "中性"

# ---- 門檻常數（可調；刻意外露成模組常數，方便日後微調） ----
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD = 30.0
KD_PERIOD = 9
KD_OVERBOUGHT = 80.0
KD_OVERSOLD = 20.0
BIAS_WIDE = 15.0   # 對 MA20 的乖離（%）過大
BIAS_MILD = 8.0
VOL_SURGE = 1.8    # 量比（當日量 / 近20日均量）爆量
VOL_DRY = 0.6      # 量縮
POS_HIGH = 80.0    # 近一年價格位階百分位
POS_LOW = 20.0
PE_HIGH = 80.0     # 本益比近年百分位
PE_LOW = 20.0
REV_STRONG = 15.0  # 月營收年增（%）
REV_WEAK = -10.0

DISCLAIMER = (
    "以上把價量、動能、籌碼、估值、基本面的『目前讀數』與傳統技術分析的解讀整理成一張表，"
    "方便你一次看全貌。市場常常不照技術面走，這不是預測，也不是買賣建議。"
)


def _to_floats(prices: Sequence[Any], key: str, *, positive: bool = False) -> list[float]:
    out: list[float] = []
    for p in prices:
        v = p.get(key) if isinstance(p, dict) else getattr(p, key, None)
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(f):
            continue
        if positive and f <= 0:
            continue
        out.append(f)
    return out


def sma(values: Sequence[float], n: int) -> float | None:
    values = [float(v) for v in values if _is_positive_number(v)]
    if len(values) < n or n <= 0:
        return None
    return sum(values[-n:]) / n


def rsi(closes: Sequence[float], period: int = RSI_PERIOD) -> float | None:
    """Wilder 平滑 RSI（業界標準，與多數看盤軟體一致）。

    先用前 period 根變動的平均當種子，之後逐根用 (前值×(period-1)+本根)/period 平滑。
    """
    closes = [float(v) for v in closes if _is_positive_number(v)]
    if len(closes) <= period:
        return None
    gains = [max(closes[i] - closes[i - 1], 0.0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0.0) for i in range(1, len(closes))]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    if avg_gain == 0:
        return 0.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 1)


def kd(prices: Sequence[Any], period: int = KD_PERIOD) -> tuple[float, float] | None:
    rows = _valid_price_rows(prices)
    highs = [row["high"] for row in rows]
    lows = [row["low"] for row in rows]
    closes = [row["close"] for row in rows]
    n = min(len(highs), len(lows), len(closes))
    if n < period:
        return None
    k = 50.0
    d = 50.0
    for i in range(period - 1, n):
        window_low = min(lows[i - period + 1 : i + 1])
        window_high = max(highs[i - period + 1 : i + 1])
        rsv = 50.0 if window_high == window_low else (closes[i] - window_low) / (window_high - window_low) * 100
        k = (2 / 3) * k + (1 / 3) * rsv
        d = (2 / 3) * d + (1 / 3) * k
    return round(k, 1), round(d, 1)


def _percentile_position(closes: Sequence[float], window: int = 240) -> float | None:
    closes = [float(v) for v in closes if _is_positive_number(v)]
    sample = closes[-window:]
    if len(sample) < 20:
        return None
    lo = min(sample)
    hi = max(sample)
    if hi == lo:
        return 50.0
    return round((closes[-1] - lo) / (hi - lo) * 100, 0)


def _factor(key: str, label: str, reading: str, lean: str, *, value: Any = None, traditional: str = "") -> dict[str, Any]:
    tone = {"偏多解讀": "bull", "偏空解讀": "bear"}.get(lean, "neutral")
    return {"key": key, "label": label, "reading": reading, "lean": lean, "tone": tone, "value": value, "traditional": traditional}


def _ma_factor(closes: list[float]) -> dict[str, Any]:
    c = closes[-1]
    ma5, ma20, ma60 = sma(closes, 5), sma(closes, 20), sma(closes, 60)
    if None in (ma5, ma20, ma60):
        return _factor("ma", "均線排列", "均線資料不足（需約 60 個交易日）。", LEAN_NEUTRAL,
                       traditional="均線是近 N 日平均收盤，用來看趨勢方向。")
    if ma5 > ma20 > ma60 and c >= ma20:
        reading = "多頭排列：MA5 > MA20 > MA60，且收盤在月線之上。"
        lean = LEAN_BULL
    elif ma5 < ma20 < ma60 and c <= ma20:
        reading = "空頭排列：MA5 < MA20 < MA60，且收盤在月線之下。"
        lean = LEAN_BEAR
    else:
        reading = "均線糾結／方向未明：短中長期均線交錯。"
        lean = LEAN_NEUTRAL
    return _factor("ma", "均線排列", reading, lean, value=f"MA5 {ma5:.2f} / MA20 {ma20:.2f} / MA60 {ma60:.2f}",
                   traditional="傳統上多頭排列視為中期偏多、空頭排列偏空；糾結時方向不明。")


def _bias_factor(closes: list[float]) -> dict[str, Any]:
    ma20 = sma(closes, 20)
    if ma20 is None or ma20 == 0:
        return _factor("bias", "乖離（對月線）", "資料不足。", LEAN_NEUTRAL)
    bias = (closes[-1] - ma20) / ma20 * 100
    if bias >= BIAS_WIDE:
        reading = f"正乖離偏大（+{bias:.1f}%），股價拉離月線較遠。"
        lean = LEAN_BEAR
        trad = "傳統上正乖離過大代表短線漲多、易回測均線（不保證）。"
    elif bias <= -BIAS_WIDE:
        reading = f"負乖離偏大（{bias:.1f}%），股價遠低於月線。"
        lean = LEAN_BULL
        trad = "傳統上負乖離過大代表短線跌深、易出現反彈（不保證）。"
    else:
        reading = f"乖離溫和（{bias:+.1f}%），貼近月線。"
        lean = LEAN_NEUTRAL
        trad = "乖離率＝收盤偏離月線的百分比，過大時傳統上易向均線靠攏。"
    return _factor("bias", "乖離（對月線）", reading, lean, value=f"{bias:+.1f}%", traditional=trad)


def _rsi_factor(closes: list[float]) -> dict[str, Any]:
    value = rsi(closes)
    if value is None:
        return _factor("rsi", "RSI 強弱", "資料不足。", LEAN_NEUTRAL)
    if value >= RSI_OVERBOUGHT:
        reading = f"RSI {value}，進入超買區（≥{RSI_OVERBOUGHT:.0f}）。"
        lean = LEAN_BEAR
        trad = "傳統上 RSI 超買代表短線動能過熱、易回檔；但強勢股也可能續強，不保證。"
    elif value <= RSI_OVERSOLD:
        reading = f"RSI {value}，進入超賣區（≤{RSI_OVERSOLD:.0f}）。"
        lean = LEAN_BULL
        trad = "傳統上 RSI 超賣代表短線跌深、易反彈；但弱勢股也可能續弱，不保證。"
    else:
        reading = f"RSI {value}，落在中性區。"
        lean = LEAN_NEUTRAL
        trad = "RSI 衡量近期漲跌動能，>70 傳統視為超買、<30 超賣。"
    return _factor("rsi", "RSI 強弱", reading, lean, value=value, traditional=trad)


def _kd_factor(prices: Sequence[Any]) -> dict[str, Any]:
    result = kd(prices)
    if result is None:
        return _factor("kd", "KD 指標", "資料不足。", LEAN_NEUTRAL)
    k, d = result
    if k >= KD_OVERBOUGHT:
        reading = f"K {k} / D {d}，K 值在超買區（≥{KD_OVERBOUGHT:.0f}）。"
        lean = LEAN_BEAR
        trad = "傳統上 KD 高檔超買易鈍化或回落（不保證）。"
    elif k <= KD_OVERSOLD:
        reading = f"K {k} / D {d}，K 值在超賣區（≤{KD_OVERSOLD:.0f}）。"
        lean = LEAN_BULL
        trad = "傳統上 KD 低檔超賣易出現反彈（不保證）。"
    else:
        reading = f"K {k} / D {d}，落在中性區。"
        lean = LEAN_NEUTRAL
        trad = "KD 由 9 日高低區間算出，>80 傳統視為超買、<20 超賣。"
    return _factor("kd", "KD 指標", reading, lean, value=f"K {k} / D {d}", traditional=trad)


def _volume_factor(prices: Sequence[Any]) -> dict[str, Any]:
    vols = _to_floats(prices, "volume", positive=True)
    if len(vols) < 20:
        return _factor("volume", "量能", "資料不足。", LEAN_NEUTRAL)
    avg20 = sum(vols[-20:]) / 20
    if avg20 <= 0:
        return _factor("volume", "量能", "近期成交量資料異常。", LEAN_NEUTRAL)
    ratio = vols[-1] / avg20
    if ratio >= VOL_SURGE:
        reading = f"當日爆量（量比 {ratio:.1f} 倍），明顯放大。"
    elif ratio <= VOL_DRY:
        reading = f"當日量縮（量比 {ratio:.1f} 倍），交投清淡。"
    else:
        reading = f"量能正常（量比 {ratio:.1f} 倍）。"
    return _factor("volume", "量能", reading, LEAN_NEUTRAL, value=f"{ratio:.1f}x",
                   traditional="量比＝當日量÷近 20 日均量。傳統上『量先價行』，爆量與量縮都需配合價格方向一起看，單看不分多空。")


def _position_factor(closes: list[float]) -> dict[str, Any]:
    pct = _percentile_position(closes)
    if pct is None:
        return _factor("position", "價格位階（近一年）", "資料不足。", LEAN_NEUTRAL)
    if pct >= POS_HIGH:
        reading = f"位階偏高：目前在近一年區間的第 {pct:.0f} 百分位。"
        lean = LEAN_BEAR
        trad = "傳統上在近年相對高位『追高』風險較大（不保證會回）。"
    elif pct <= POS_LOW:
        reading = f"位階偏低：目前在近一年區間的第 {pct:.0f} 百分位。"
        lean = LEAN_BULL
        trad = "傳統上在近年相對低位『相對抗跌』，但弱勢股也可能再破底（不保證）。"
    else:
        reading = f"位階居中：目前在近一年區間的第 {pct:.0f} 百分位。"
        lean = LEAN_NEUTRAL
        trad = "位階＝目前收盤落在近一年最高最低之間的相對位置。"
    return _factor("position", "價格位階（近一年）", reading, lean, value=f"{pct:.0f}%", traditional=trad)


def _chips_factor(chips: dict[str, Any] | None) -> dict[str, Any] | None:
    if not chips or not chips.get("available"):
        return None
    level = chips.get("level")
    consec = chips.get("consecutive_total_sell_days", 0)
    sum20 = (chips.get("sum_20") or {}).get("total_net", 0)
    if level in ("警戒", "注意"):
        reading = f"籌碼面{level}：三大法人近期偏賣方（連續賣超約 {consec} 天）。"
        lean = LEAN_BEAR
    elif sum20 and sum20 > 0 and (level in ("無", "留意")):
        reading = "近 20 日三大法人合計買超，籌碼面暫時偏穩。"
        lean = LEAN_BULL
    else:
        reading = "三大法人近期買賣超方向不明確。"
        lean = LEAN_NEUTRAL
    return _factor("chips", "籌碼（三大法人）", reading, lean,
                   traditional="傳統上法人持續買超視為籌碼偏穩、持續賣超偏弱；但法人也可能因避險、調節而進出。")


def _valuation_factor(valuation: dict[str, Any] | None) -> dict[str, Any] | None:
    bands = (valuation or {}).get("bands") if valuation else None
    pe = (bands or {}).get("pe") if bands else None
    if not pe or not pe.get("available") or pe.get("current_percentile") is None:
        return None
    pct = float(pe["current_percentile"])
    if pct >= PE_HIGH:
        reading = f"本益比在近年相對高位（第 {pct:.0f} 百分位）。"
        lean = LEAN_BEAR
    elif pct <= PE_LOW:
        reading = f"本益比在近年相對低位（第 {pct:.0f} 百分位）。"
        lean = LEAN_BULL
    else:
        reading = f"本益比在近年區間中段（第 {pct:.0f} 百分位）。"
        lean = LEAN_NEUTRAL
    return _factor("valuation", "估值位階（本益比）", reading, lean, value=f"{pct:.0f}%",
                   traditional="只比自己歷史：目前倍數落在近年第幾百分位。位階高低只是相對位置，不代表貴或便宜。")


def _fundamental_factor(revenue_summary: dict[str, Any] | None, financial_summary: dict[str, Any] | None) -> dict[str, Any] | None:
    rev = revenue_summary or {}
    yoy = None
    for fact in rev.get("facts", []) or []:
        if fact.get("label") == "年增率":
            yoy = fact.get("value")
    if yoy is None:
        return None
    try:
        yoy = float(yoy)
    except (TypeError, ValueError):
        return None
    if yoy >= REV_STRONG:
        reading = f"最新月營收年增 {yoy:+.1f}%，營收動能強。"
        lean = LEAN_BULL
    elif yoy <= REV_WEAK:
        reading = f"最新月營收年增 {yoy:+.1f}%，營收動能轉弱。"
        lean = LEAN_BEAR
    else:
        reading = f"最新月營收年增 {yoy:+.1f}%，營收動能持平。"
        lean = LEAN_NEUTRAL
    return _factor("fundamental", "基本面（營收動能）", reading, lean, value=f"{yoy:+.1f}%",
                   traditional="月營收年增反映生意量擴張或收縮，是基本面的領先指標之一。")


def build_assessment(
    prices: Sequence[Any],
    *,
    valuation: dict[str, Any] | None = None,
    chips: dict[str, Any] | None = None,
    revenue_summary: dict[str, Any] | None = None,
    financial_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """回傳體質總評 dict。固定輸入→固定輸出，純函數、可單元測試。"""
    rows = _valid_price_rows(prices)
    closes = [row["close"] for row in rows]
    if len(closes) < 20:
        return {"available": False, "summary": "日線資料不足（需約 20 個交易日），先同步更多資料再做體質總評。",
                "counts": {"bull": 0, "bear": 0, "neutral": 0}, "factors": [], "disclaimer": DISCLAIMER}

    factors: list[dict[str, Any]] = [
        _ma_factor(closes),
        _bias_factor(closes),
        _rsi_factor(closes),
        _kd_factor(rows),
        _volume_factor(rows),
        _position_factor(closes),
    ]
    for extra in (_chips_factor(chips), _valuation_factor(valuation), _fundamental_factor(revenue_summary, financial_summary)):
        if extra is not None:
            factors.append(extra)

    bull = sum(1 for f in factors if f["lean"] == LEAN_BULL)
    bear = sum(1 for f in factors if f["lean"] == LEAN_BEAR)
    neutral = len(factors) - bull - bear
    if bull > bear:
        tilt = "目前以『偏多解讀』的因子居多"
    elif bear > bull:
        tilt = "目前以『偏空解讀』的因子居多"
    else:
        tilt = "目前多空解讀的因子大致均衡"
    summary = (
        f"綜合 {len(factors)} 個面向：傳統上偏多解讀 {bull} 項、偏空解讀 {bear} 項、中性 {neutral} 項，{tilt}。"
        "這只是把各面向的傳統解讀做個清點，不是預測，也不是買賣建議。"
    )
    return {
        "available": True,
        "counts": {"bull": bull, "bear": bear, "neutral": neutral},
        "summary": summary,
        "factors": factors,
        "disclaimer": DISCLAIMER,
    }


def _is_positive_number(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0


def _valid_price_rows(prices: Sequence[Any]) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for item in prices or []:
        high = _field_float(item, "high")
        low = _field_float(item, "low")
        close = _field_float(item, "close")
        if high is None or low is None or close is None:
            continue
        if high <= 0 or low <= 0 or close <= 0 or high < low:
            continue
        if close < low or close > high:
            continue
        open_price = _field_float(item, "open")
        volume = _field_float(item, "volume")
        if _looks_like_halt_row(open_price, high, low, close, volume):
            continue
        rows.append({
            "open": open_price if open_price is not None else close,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume if volume is not None else 0.0,
        })
    return rows


def _field_float(item: Any, key: str) -> float | None:
    value = item.get(key) if isinstance(item, dict) else getattr(item, key, None)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _looks_like_halt_row(
    open_price: float | None,
    high: float,
    low: float,
    close: float,
    volume: float | None,
) -> bool:
    if volume != 0:
        return False
    o = close if open_price is None else open_price
    return o == high == low == close
