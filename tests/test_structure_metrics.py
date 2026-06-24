"""結構指紋估計子的合成訊號校準測試。

用已知性質的訊號驗證估計子落在預期範圍：
- 白噪音報酬 → Hurst≈0.5、排列熵≈1、樣本熵高
- 隨機漫步（當作報酬輸入）→ Hurst≈1.5
- 正弦 → 排列熵/樣本熵低
- log 價格為隨機漫步 → 譜斜率 β≈2；白噪音 → β≈0
"""
import math
import random

from app.analyze.structure_metrics import (
    build_structure_fingerprint,
    hurst_dfa,
    permutation_entropy,
    realized_vol_percentile,
    sample_entropy,
    spectral_slope,
    volatility_clustering,
)


def _white(n, seed=7):
    rng = random.Random(seed)
    return [rng.gauss(0, 1) for _ in range(n)]


def _random_walk(n, seed=7):
    rng = random.Random(seed)
    out, s = [], 0.0
    for _ in range(n):
        s += rng.gauss(0, 1)
        out.append(s)
    return out


def _ar1(n, phi=0.6, seed=7):
    rng = random.Random(seed)
    out = [0.0]
    for _ in range(n - 1):
        out.append(phi * out[-1] + rng.gauss(0, 1))
    return out


def _sine(n):
    return [math.sin(2 * math.pi * i / 20) + 0.05 * math.cos(i) for i in range(n)]


def test_hurst_white_noise_near_half():
    snap = hurst_dfa(_white(1000))
    assert snap.available
    assert 0.42 <= snap.value <= 0.60
    assert snap.confidence > 0.9


def test_hurst_random_walk_near_one_and_half():
    snap = hurst_dfa(_random_walk(1000))
    assert snap.available
    assert 1.30 <= snap.value <= 1.70


def test_hurst_ar1_persistent_above_half():
    snap = hurst_dfa(_ar1(1000))
    assert snap.available
    assert snap.value > 0.55


def test_permutation_entropy_white_high():
    snap = permutation_entropy(_white(1000))
    assert snap.available
    assert snap.value > 0.95


def test_permutation_entropy_sine_low():
    snap = permutation_entropy(_sine(1000))
    assert snap.available
    assert snap.value < 0.75


def test_sample_entropy_white_higher_than_sine():
    white = sample_entropy(_white(1000))
    sine = sample_entropy(_sine(1000))
    assert white.available and sine.available
    assert white.value > sine.value
    assert white.value > 1.2
    assert sine.value < 0.8


def test_spectral_slope_random_walk_near_two():
    snap = spectral_slope([math.exp(v) for v in _random_walk(1024)])
    assert snap.available
    assert 1.5 <= snap.value <= 2.4


def test_spectral_slope_white_near_zero():
    # log 價格為白噪音（圍繞一個正水準）→ β≈0
    snap = spectral_slope([100 + v for v in _white(1024)])
    assert snap.available
    assert snap.value < 0.4


def test_volatility_clustering_nonnegative():
    snap = volatility_clustering(_white(500))
    assert snap.available
    assert snap.value >= 0.0


def test_realized_vol_percentile_in_range():
    snap = realized_vol_percentile(_white(500))
    assert snap.available
    assert 0.0 <= snap.value <= 100.0


def test_graceful_degradation_short_series():
    snap = hurst_dfa(_white(50))
    assert not snap.available
    assert snap.value is None
    assert "樣本不足" in snap.reason


def test_build_fingerprint_shape():
    closes = [math.exp(v * 0.01) * 100 for v in _random_walk(600)]
    fp = build_structure_fingerprint(closes)
    assert fp["available"]
    assert fp["synchrony_locked"] is True
    assert len(fp["dimensions"]) == 5
    for dim in fp["dimensions"]:
        assert "label" in dim and "snapshot" in dim
    assert "不是預測" in fp["disclaimer"]
