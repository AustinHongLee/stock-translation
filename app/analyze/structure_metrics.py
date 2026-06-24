"""結構指紋（Structure Fingerprint）：把 OHLCV 翻成「市場結構描述」的純函數核。

定位：結構顯微鏡，只描述當下狀態，**不預測、不給買賣訊號**。
所有估計子輸入一律為 log return（除 spectral_slope 用 log price）。
純 Python（只用標準庫），不引入 numpy/scipy，維持與專案一致、不增打包體積。
固定輸入 → 固定輸出；資料不足時回傳 available=False，不丟例外。

每個估計子已在合成訊號上校準（見 tests/test_structure_metrics.py）：
白噪音報酬 H≈0.5、隨機漫步 H≈1.5、白噪音 PermEnt≈1、隨機漫步 log 價格 β≈2 等。
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any, Sequence

# 各估計子的最小樣本門檻
MIN_N_DFA = 120
MIN_N_PERM = 120
MIN_N_SAMPEN = 200
MIN_N_SPECTRAL = 256
MIN_N_VCI = 150
MIN_N_RV = 60
MIN_N_MFDFA = 500


@dataclass(frozen=True, slots=True)
class MetricSnapshot:
    """單一結構量的結果。value 為 None 表示資料不足/無法計算。"""

    key: str
    value: float | None
    available: bool
    confidence: float            # 0..1（樣本充足度 / 擬合 R²）
    reason: str                  # 不可用時的診斷；可用時為簡短註記
    reading: str = ""            # 白話解讀（描述，非預測）
    forbidden: str = ""          # 明確的「不得解讀為」

    def to_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": None if self.value is None else round(self.value, 4),
            "available": self.available,
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
            "reading": self.reading,
            "forbidden": self.forbidden,
        }


def _unavailable(key: str, reason: str) -> MetricSnapshot:
    return MetricSnapshot(key=key, value=None, available=False, confidence=0.0, reason=reason)


def _clean(values: Sequence[float]) -> list[float]:
    out: list[float] = []
    for v in values or []:
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(f):
            out.append(f)
    return out


def _mean(a: Sequence[float]) -> float:
    return sum(a) / len(a)


def _std(a: Sequence[float]) -> float:
    if len(a) < 2:
        return 0.0
    m = _mean(a)
    return math.sqrt(sum((x - m) ** 2 for x in a) / (len(a) - 1))


def _linfit(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float, float]:
    """回傳 (slope, intercept, R^2)。"""
    n = len(xs)
    if n < 2:
        return 0.0, 0.0, 0.0
    mx = _mean(xs)
    my = _mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx if sxx else 0.0
    inter = my - slope * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + inter)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    return slope, inter, r2


def log_returns(closes: Sequence[float]) -> list[float]:
    c = _clean(closes)
    out: list[float] = []
    for i in range(1, len(c)):
        if c[i] > 0 and c[i - 1] > 0:
            out.append(math.log(c[i] / c[i - 1]))
    return out


def _log_scales(lo: int, hi: int, count: int = 15) -> list[int]:
    if hi <= lo:
        return [lo]
    a, b = math.log10(lo), math.log10(hi)
    return sorted({int(round(10 ** (a + i * (b - a) / (count - 1)))) for i in range(count)})


# ---------------------------------------------------------------------------
# 估計子
# ---------------------------------------------------------------------------

def hurst_dfa(returns: Sequence[float], *, order: int = 1) -> MetricSnapshot:
    """DFA-1 去趨勢波動分析，斜率 α≈Hurst 指數。記憶性維度。"""
    x = _clean(returns)
    n = len(x)
    if n < MIN_N_DFA:
        return _unavailable("hurst_dfa", f"樣本不足 N={n}（需 ≥ {MIN_N_DFA}）。")
    mean = _mean(x)
    profile: list[float] = []
    s = 0.0
    for v in x:
        s += v - mean
        profile.append(s)
    scales = _log_scales(8, n // 4)
    logn: list[float] = []
    logf: list[float] = []
    for scale in scales:
        if scale < order + 2:
            continue
        nseg = n // scale
        if nseg < 1:
            continue
        acc = 0.0
        cnt = 0
        for seg_i in range(nseg):
            seg = profile[seg_i * scale:(seg_i + 1) * scale]
            t = list(range(scale))
            sl, ic, _ = _linfit(t, seg)
            acc += sum((seg[j] - (sl * j + ic)) ** 2 for j in range(scale))
            cnt += scale
        f = math.sqrt(acc / cnt) if cnt else 0.0
        if f > 0:
            logn.append(math.log(scale))
            logf.append(math.log(f))
    if len(logn) < 4:
        return _unavailable("hurst_dfa", "可用尺度不足。")
    slope, _, r2 = _linfit(logn, logf)
    if slope >= 0.55:
        reading = f"H={slope:.2f}：延續性偏高，傾向延續近期行為。"
    elif slope <= 0.45:
        reading = f"H={slope:.2f}：偏反持久，傾向高頻自我修正/回擺。"
    else:
        reading = f"H={slope:.2f}：接近隨機漫步（記憶已耗散）。"
    return MetricSnapshot(
        key="hurst_dfa", value=slope, available=True, confidence=max(0.0, min(1.0, r2)),
        reason=f"擬合 R²={r2:.3f}", reading=reading,
        forbidden="不得解讀為『會繼續漲』或『一定反轉』；H 描述自相關結構，不含方向。",
    )


def permutation_entropy(returns: Sequence[float], *, d: int = 4, tau: int = 1) -> MetricSnapshot:
    """正規化排列熵（序數型態），複雜度維度。對單調變換不變、抗噪。"""
    x = _clean(returns)
    n = len(x)
    if n < max(MIN_N_PERM, d * math.factorial(d) // 4):
        return _unavailable("permutation_entropy", f"樣本不足 N={n}（d={d} 需更多樣本）。")
    counts: Counter[tuple[int, ...]] = Counter()
    span = (d - 1) * tau
    for i in range(n - span):
        # 以 (值, 索引) 排序，索引作為平手的決定性 tie-break
        window = sorted(((x[i + j * tau], j) for j in range(d)))
        pattern = tuple(idx for _, idx in window)
        counts[pattern] += 1
    total = sum(counts.values())
    entropy = -sum((v / total) * math.log(v / total) for v in counts.values())
    pe = entropy / math.log(math.factorial(d))
    if pe >= 0.9:
        reading = f"PE={pe:.2f}：高複雜度，接近隨機（無可辨識順序結構）。"
    elif pe <= 0.6:
        reading = f"PE={pe:.2f}：低複雜度，順序結構明顯（行為較格式化）。"
    else:
        reading = f"PE={pe:.2f}：中等複雜度。"
    conf = max(0.0, min(1.0, (n - 120) / 880))  # N 越多越穩
    return MetricSnapshot(
        key="permutation_entropy", value=pe, available=True, confidence=conf,
        reason=f"d={d}, tau={tau}, N={n}", reading=reading,
        forbidden="低複雜度 ≠ 可預測、可獲利；只描述順序結構的規律程度。",
    )


def sample_entropy(returns: Sequence[float], *, m: int = 2, r_mult: float = 0.2) -> MetricSnapshot:
    """樣本熵：資訊生成速率/不可壓縮性。複雜度維度（與 PE 互為佐證）。"""
    x = _clean(returns)
    n = len(x)
    if n < MIN_N_SAMPEN:
        return _unavailable("sample_entropy", f"樣本不足 N={n}（需 ≥ {MIN_N_SAMPEN}）。")
    r = r_mult * _std(x)
    if r <= 0:
        return _unavailable("sample_entropy", "序列無變異（std=0）。")

    def count_matches(mm: int) -> int:
        templates = [x[i:i + mm] for i in range(n - mm + 1)]
        total = 0
        length = len(templates)
        for i in range(length):
            ti = templates[i]
            for j in range(i + 1, length):
                tj = templates[j]
                if all(abs(ti[k] - tj[k]) < r for k in range(mm)):
                    total += 1
        return total

    b = count_matches(m)
    a = count_matches(m + 1)
    if b == 0 or a == 0:
        return _unavailable("sample_entropy", "匹配對不足，無法估計。")
    value = -math.log(a / b)
    reading = (
        f"SampEn={value:.2f}：高不規律/難壓縮。" if value >= 1.2
        else f"SampEn={value:.2f}：較規律、重複性高。"
    )
    return MetricSnapshot(
        key="sample_entropy", value=value, available=True, confidence=0.7,
        reason=f"m={m}, r={r:.4f}", reading=reading,
        forbidden="不得當訊號；與排列熵一起看『複雜度』維度。",
    )


def spectral_slope(closes: Sequence[float]) -> MetricSnapshot:
    """log 價格功率譜的 1/f 斜率 β（Hann 窗周期圖）。噪音顏色維度。"""
    c = _clean(closes)
    logp = [math.log(v) for v in c if v > 0]
    n = len(logp)
    if n < MIN_N_SPECTRAL:
        return _unavailable("spectral_slope", f"樣本不足 N={n}（需 ≥ {MIN_N_SPECTRAL}）。")
    mean = _mean(logp)
    win = [(logp[i] - mean) * (0.5 - 0.5 * math.cos(2 * math.pi * i / (n - 1))) for i in range(n)]
    half = n // 2
    freqs: list[float] = []
    power: list[float] = []
    for k in range(1, half):
        ang = -2 * math.pi * k / n
        re = sum(win[t] * math.cos(ang * t) for t in range(n))
        im = sum(win[t] * math.sin(ang * t) for t in range(n))
        freqs.append(k / n)
        power.append(re * re + im * im)
    band = [(f, p) for f, p in zip(freqs, power) if 0.025 <= f <= 0.225 and p > 0]
    if len(band) < 8:
        return _unavailable("spectral_slope", "中頻帶點數不足。")
    lf = [math.log(f) for f, _ in band]
    lp = [math.log(p) for _, p in band]
    slope, _, r2 = _linfit(lf, lp)
    beta = -slope
    if beta <= 0.5:
        reading = f"β={beta:.2f}：偏白噪音（破碎、無結構）。"
    elif beta >= 1.5:
        reading = f"β={beta:.2f}：偏紅/布朗噪音（平滑、趨勢粘滯）。"
    else:
        reading = f"β={beta:.2f}：接近 1/f 粉紅噪音（秩序與隨機之間）。"
    return MetricSnapshot(
        key="spectral_slope", value=beta, available=True, confidence=max(0.0, min(1.0, r2)),
        reason=f"擬合 R²={r2:.3f}", reading=reading,
        forbidden="不得當作週期或轉折預告。",
    )


def volatility_clustering(returns: Sequence[float], *, k_max: int = 20) -> MetricSnapshot:
    """|報酬| 的自相關和（顯著正落後），波動聚集/長記憶維度。"""
    x = _clean(returns)
    n = len(x)
    if n < MIN_N_VCI:
        return _unavailable("volatility_clustering", f"樣本不足 N={n}（需 ≥ {MIN_N_VCI}）。")
    a = [abs(v) for v in x]
    m = _mean(a)
    denom = sum((v - m) ** 2 for v in a)
    if denom <= 0:
        return _unavailable("volatility_clustering", "序列無變異。")
    thr = 2 / math.sqrt(n)
    idx = 0.0
    for lag in range(1, k_max + 1):
        num = sum((a[t] - m) * (a[t - lag] - m) for t in range(lag, n))
        rho = num / denom
        if rho > thr:
            idx += rho
    reading = (
        f"VCI={idx:.2f}：波動聚集明顯（大波後常接大波）。" if idx >= 1.0
        else f"VCI={idx:.2f}：波動聚集不明顯。"
    )
    return MetricSnapshot(
        key="volatility_clustering", value=idx, available=True, confidence=0.8,
        reason=f"k_max={k_max}", reading=reading,
        forbidden="不得解讀為『即將大漲大跌』；只描述波動的聚集性。",
    )


def realized_vol_percentile(returns: Sequence[float], *, window: int = 20) -> MetricSnapshot:
    """滾動已實現波動（年化）在自身歷史的百分位。湍流（快）維度。"""
    x = _clean(returns)
    n = len(x)
    if n < window * 3:
        return _unavailable("realized_vol_percentile", f"樣本不足 N={n}（需 ≥ {window * 3}）。")
    rv = [_std(x[i - window:i]) * math.sqrt(252) for i in range(window, n + 1)]
    cur = rv[-1]
    pct = 100.0 * sum(1 for v in rv if v <= cur) / len(rv)
    reading = (
        f"RV 百分位={pct:.0f}%：波動處於歷史高檔（較『亂』）。" if pct >= 70
        else f"RV 百分位={pct:.0f}%：波動處於歷史{'低' if pct <= 30 else '中'}檔。"
    )
    return MetricSnapshot(
        key="realized_vol_percentile", value=pct, available=True, confidence=0.85,
        reason=f"window={window}", reading=reading,
        forbidden="高波動不等於方向判斷；只描述目前波動相對自身歷史的位置。",
    )


# ---------------------------------------------------------------------------
# 指紋卡組裝
# ---------------------------------------------------------------------------

_DIMENSIONS = (
    ("memory", "延續性", "hurst_dfa"),
    ("complexity", "複雜度", "permutation_entropy"),
    ("agitation", "波動聚集", "volatility_clustering"),
    ("chroma", "噪音色", "spectral_slope"),
    ("turbulence", "湍流程度", "realized_vol_percentile"),
)

DISCLAIMER = "這是結構描述，不是預測，也不是買賣建議。"


def confidence_grade(snap: "MetricSnapshot") -> str:
    """把 0..1 的 confidence 對映成 UI 三級，避免被誤讀成『準確率』。"""
    if not snap.available:
        return "insufficient"
    if snap.confidence >= 0.7:
        return "high"
    if snap.confidence >= 0.4:
        return "medium"
    return "low"


def _level_0_5(key: str, value: float | None) -> int | None:
    """把指標值映射成 0–5 顯示格數（display-only；真值與解讀以 value/reading 為準）。"""
    if value is None:
        return None
    if key == "hurst_dfa":              # 0.3..1.0 -> 0..5（離隨機越遠/越粘滯越高）
        return _scale(value, 0.3, 1.0)
    if key == "permutation_entropy":    # 0.4..1.0 -> 0..5
        return _scale(value, 0.4, 1.0)
    if key == "volatility_clustering":  # 0..3 -> 0..5
        return _scale(value, 0.0, 3.0)
    if key == "spectral_slope":         # 0..2 -> 0..5
        return _scale(value, 0.0, 2.0)
    if key == "realized_vol_percentile":
        return _scale(value, 0.0, 100.0)
    return None


def _scale(value: float, lo: float, hi: float) -> int:
    if hi <= lo:
        return 0
    return max(0, min(5, round((value - lo) / (hi - lo) * 5)))


def build_structure_fingerprint(closes: Sequence[float]) -> dict[str, Any]:
    """從收盤序列算出結構指紋卡（MVP 六維中目前實作 5 維；同步性需跨股資料）。"""
    rets = log_returns(closes)
    # 只計算會顯示的維度，避免做了 O(N²) 的 SampEn 卻不呈現（SampEn 函式保留給進階/API 另呼叫）。
    metrics = {
        "hurst_dfa": hurst_dfa(rets),
        "permutation_entropy": permutation_entropy(rets),
        "volatility_clustering": volatility_clustering(rets),
        "spectral_slope": spectral_slope(closes),
        "realized_vol_percentile": realized_vol_percentile(rets),
    }
    dimensions = []
    for dim_key, label, source_key in _DIMENSIONS:
        snap = metrics[source_key]
        dimensions.append({
            "key": dim_key,
            "label": label,
            "source": source_key,
            "level": _level_0_5(source_key, snap.value),
            "grade": confidence_grade(snap),
            "snapshot": snap.to_json(),
        })
    return {
        "available": any(m.available for m in metrics.values()),
        "return_count": len(rets),
        "dimensions": dimensions,
        "metrics": {k: v.to_json() for k, v in metrics.items()},
        "synchrony_locked": True,   # 同步性需 D1 跨股資料，MVP 鎖定
        "disclaimer": DISCLAIMER,
    }
