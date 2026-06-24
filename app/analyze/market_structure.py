"""Market-level structure metrics for Market Mind Radar."""
from __future__ import annotations

import math
from typing import Any

from app.analyze.cross_section import ReturnsMatrix
from app.analyze.structure_metrics import MetricSnapshot


TITLE = "市場心智雷達"
SUBTITLE = "現在整個市場的結構狀態（描述，非預測）"
DISCLAIMER = "市場結構描述 · 描述現在 · 不預測未來 · 非投資建議"
INSUFFICIENT_REASON = "資料不足，請先在「本地資料」完成全市場下載（至少 30 檔、近 60 個交易日）。"


def cross_sectional_dispersion(matrix: ReturnsMatrix) -> MetricSnapshot:
    rows = _valid_rows(matrix)
    if not rows:
        return _unavailable("dispersion", "沒有可用報酬列。")
    dispersions = [_std(row) for row in rows]
    latest = dispersions[-1]
    percentile = _percentile_rank(dispersions, latest)
    if percentile >= 70:
        reading = "今天個股之間分化偏大，各走各的程度較高。"
    elif percentile <= 30:
        reading = "今天個股之間分化偏低，整體動得較接近。"
    else:
        reading = "今天個股分化在近期中段。"
    return MetricSnapshot(
        key="dispersion",
        value=latest,
        available=True,
        confidence=1.0,
        reason=f"percentile={percentile:.1f}",
        reading=reading,
        forbidden="不得當變盤訊號；只描述個股之間分化程度。",
    )


def average_pairwise_correlation(matrix: ReturnsMatrix) -> MetricSnapshot:
    corr = correlation_matrix(matrix)
    if len(corr) < 2:
        return _unavailable("herding", "可用股票數不足。")
    total = 0.0
    count = 0
    for i in range(len(corr)):
        for j in range(i + 1, len(corr)):
            total += corr[i][j]
            count += 1
    value = total / count if count else 0.0
    if value >= 0.5:
        reading = f"平均成對相關 {value:.2f}：市場連動偏高，分散效果較弱。"
    elif value <= 0.15:
        reading = f"平均成對相關 {value:.2f}：個股較各自表現。"
    else:
        reading = f"平均成對相關 {value:.2f}：市場連動在中段。"
    return MetricSnapshot(
        key="herding",
        value=value,
        available=True,
        confidence=1.0,
        reason=f"pairs={count}",
        reading=reading,
        forbidden="高相關不等於方向判斷；只描述連動程度。",
    )


def market_mode_share(matrix: ReturnsMatrix) -> MetricSnapshot:
    corr = correlation_matrix(matrix)
    m = len(corr)
    if m < 2:
        return _unavailable("synchrony", "可用股票數不足。")
    largest = largest_eigenvalue_power(corr)
    share = largest / m if m else 0.0
    if share >= 0.45:
        reading = f"最大模態佔 {share * 100:.0f}%：共同因子影響偏高，同步性強。"
    elif share <= 0.18:
        reading = f"最大模態佔 {share * 100:.0f}%：沒有明顯單一主導力量。"
    else:
        reading = f"最大模態佔 {share * 100:.0f}%：共同因子影響在中段。"
    return MetricSnapshot(
        key="synchrony",
        value=share,
        available=True,
        confidence=1.0,
        reason=f"lambda1={largest:.4f}, stocks={m}",
        reading=reading,
        forbidden="不得當方向或時點訊號；只描述共同因子佔比。",
    )


def build_market_radar_metrics(matrix: ReturnsMatrix) -> list[dict[str, Any]]:
    dispersion = cross_sectional_dispersion(matrix)
    herding = average_pairwise_correlation(matrix)
    synchrony = market_mode_share(matrix)
    return [
        _metric_payload(
            dispersion,
            label="市場波動(分化)",
            glossary_term="市場波動(分化)",
            percentile=_reason_percentile(dispersion.reason),
        ),
        _metric_payload(herding, label="羊群程度", glossary_term="羊群程度"),
        _metric_payload(synchrony, label="同步度", glossary_term="同步度"),
    ]


def correlation_matrix(matrix: ReturnsMatrix) -> list[list[float]]:
    rows = _valid_rows(matrix)
    if not rows:
        return []
    columns = _transpose(rows)
    standardized: list[list[float]] = []
    for col in columns:
        centered = [value - _mean(col) for value in col]
        norm = math.sqrt(sum(value * value for value in centered))
        if norm <= 0:
            continue
        standardized.append([value / norm for value in centered])
    m = len(standardized)
    corr = [[0.0 for _ in range(m)] for _ in range(m)]
    for i in range(m):
        corr[i][i] = 1.0
        for j in range(i + 1, m):
            value = sum(a * b for a, b in zip(standardized[i], standardized[j]))
            value = max(-1.0, min(1.0, value))
            corr[i][j] = corr[j][i] = value
    return corr


def largest_eigenvalue_power(matrix: list[list[float]], *, max_iter: int = 200, tol: float = 1e-10) -> float:
    n = len(matrix)
    if n == 0:
        return 0.0
    if any(len(row) != n for row in matrix):
        raise ValueError("matrix must be square")
    inv = 1.0 / math.sqrt(n)
    vec = [inv for _ in range(n)]
    last_lambda = 0.0
    for _ in range(max_iter):
        nxt = [sum(matrix[i][j] * vec[j] for j in range(n)) for i in range(n)]
        norm = math.sqrt(sum(value * value for value in nxt))
        if norm <= 0:
            return 0.0
        vec = [value / norm for value in nxt]
        lam = _rayleigh(matrix, vec)
        if abs(lam - last_lambda) <= tol:
            return lam
        last_lambda = lam
    return _rayleigh(matrix, vec)


def _metric_payload(
    snap: MetricSnapshot,
    *,
    label: str,
    glossary_term: str,
    percentile: float | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "key": snap.key,
        "label": label,
        "value": None if snap.value is None else round(snap.value, 4),
        "grade": "high" if snap.available else "insufficient",
        "summary": snap.reading,
        "forbidden": snap.forbidden,
        "glossary_term": glossary_term,
    }
    if percentile is not None:
        payload["percentile"] = round(percentile, 1)
    return payload


def _valid_rows(matrix: ReturnsMatrix) -> list[list[float]]:
    rows: list[list[float]] = []
    width = len(matrix.stock_ids)
    for row in matrix.returns:
        if len(row) != width:
            continue
        clean = []
        for value in row:
            number = float(value)
            if not math.isfinite(number):
                clean = []
                break
            clean.append(number)
        if clean:
            rows.append(clean)
    return rows


def _transpose(rows: list[list[float]]) -> list[list[float]]:
    if not rows:
        return []
    return [[row[col] for row in rows] for col in range(len(rows[0]))]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def _percentile_rank(values: list[float], current: float) -> float:
    if not values:
        return 0.0
    return 100.0 * sum(1 for value in values if value <= current) / len(values)


def _rayleigh(matrix: list[list[float]], vec: list[float]) -> float:
    product = [sum(matrix[i][j] * vec[j] for j in range(len(vec))) for i in range(len(vec))]
    return sum(a * b for a, b in zip(vec, product))


def _reason_percentile(reason: str) -> float | None:
    prefix = "percentile="
    if not reason.startswith(prefix):
        return None
    try:
        return float(reason.removeprefix(prefix))
    except ValueError:
        return None


def _unavailable(key: str, reason: str) -> MetricSnapshot:
    return MetricSnapshot(
        key=key,
        value=None,
        available=False,
        confidence=0.0,
        reason=reason,
        reading=reason,
        forbidden="不得當成方向或操作訊號。",
    )
