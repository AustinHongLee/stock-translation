"""Registry for chart indicator metadata.

The chart UI should read this catalog instead of hard-coding labels, groups,
default visibility, and risk framing for every computed feature.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class IndicatorSpec:
    key: str
    label: str
    category: str
    display_type: str
    default_enabled: bool
    risk_level: int
    description: str
    required_bars: int = 1


CATEGORY_ORDER: tuple[tuple[str, str], ...] = (
    ("price", "基礎價格"),
    ("candle", "K棒結構"),
    ("gap", "缺口"),
    ("returns", "報酬率"),
    ("sma", "SMA 均線"),
    ("ema", "EMA 均線"),
    ("ma_state", "均線狀態"),
    ("momentum", "動能"),
    ("volatility", "波動"),
    ("volume", "成交量"),
    ("volume_price", "量價關係"),
    ("rolling_sr", "滾動支撐壓力"),
    ("breakout", "突破"),
    ("rsi", "RSI"),
    ("macd", "MACD"),
    ("kd", "KD"),
    ("bollinger", "布林通道"),
    ("trend", "趨勢結構"),
    ("patterns", "型態辨識"),
    ("scores", "評分"),
)


def _spec(
    key: str,
    label: str,
    category: str,
    display_type: str,
    description: str,
    *,
    default_enabled: bool = False,
    required_bars: int = 1,
    risk_level: int = 1,
) -> IndicatorSpec:
    return IndicatorSpec(
        key=key,
        label=label,
        category=category,
        display_type=display_type,
        default_enabled=default_enabled,
        risk_level=risk_level,
        description=description,
        required_bars=required_bars,
    )


FEATURE_SPECS: tuple[IndicatorSpec, ...] = (
    _spec("previous_close", "前一日收盤", "price", "value", "前一個有效交易日的收盤價。", required_bars=2),
    _spec("price_change", "漲跌", "price", "value", "今日收盤減前一日收盤。", required_bars=2),
    _spec("price_change_percent", "漲跌幅", "price", "value", "今日漲跌除以前一日收盤，單位為百分比。", required_bars=2),
    _spec("typical_price", "典型價格", "price", "value", "(最高 + 最低 + 收盤) / 3。"),
    _spec("weighted_price", "加權價格 HLCC", "price", "value", "(最高 + 最低 + 2 * 收盤) / 4。"),
    _spec("mid_price", "中間價", "price", "value", "(最高 + 最低) / 2。"),
    _spec("body_size", "實體大小", "candle", "value", "收盤與開盤的絕對差。"),
    _spec("candle_range", "全日振幅", "candle", "value", "最高價減最低價。"),
    _spec("body_ratio", "實體占比", "candle", "value", "實體大小除以全日振幅。"),
    _spec("upper_shadow", "上影線", "candle", "value", "最高價減去開盤/收盤較高者。"),
    _spec("lower_shadow", "下影線", "candle", "value", "開盤/收盤較低者減最低價。"),
    _spec("upper_shadow_ratio", "上影線占比", "candle", "value", "上影線除以全日振幅。"),
    _spec("lower_shadow_ratio", "下影線占比", "candle", "value", "下影線除以全日振幅。"),
    _spec("bullish", "收紅 K", "candle", "flag", "收盤價高於開盤價。"),
    _spec("bearish", "收黑 K", "candle", "flag", "收盤價低於開盤價。"),
    _spec("doji", "十字線", "candle", "flag", "實體占全日振幅小於 10%，僅為單根 K 參考。"),
    _spec("long_body", "長實體", "candle", "flag", "實體占全日振幅大於 70%。"),
    _spec("marubozu", "光頭光腳", "candle", "flag", "上下影線都很短且實體偏長。"),
    _spec("hammer", "錘子線", "candle", "flag", "長下影、短上影、實體在上緣的單根 K 參考。"),
    _spec("inverted_hammer", "倒錘子線", "candle", "flag", "長上影、短下影、實體在下緣的單根 K 參考。"),
    _spec("shooting_star", "流星線", "candle", "flag", "形狀同倒錘子，需另搭配趨勢脈絡判讀。"),
    _spec("hanging_man", "吊人線", "candle", "flag", "形狀同錘子線，需另搭配趨勢脈絡判讀。"),
    _spec("spinning_top", "紡錘線", "candle", "flag", "小實體且上下影線都大於實體。"),
    *(
        _spec(f"return_{period}d", f"{period}日報酬", "returns", "value", f"收盤相對 {period} 個交易日前的報酬率。", required_bars=period + 1)
        for period in (1, 3, 5, 10, 20, 60, 120, 250)
    ),
    _spec("return_ytd", "今年以來報酬", "returns", "value", "相對當年度第一個有效交易日收盤的報酬率。"),
    _spec("return_52w", "近52週報酬", "returns", "value", "同 250 日報酬率。", required_bars=251),
    *(
        _spec(f"ma{period}", f"MA{period}", "sma", "overlay", f"近 {period} 根收盤價簡單平均。", default_enabled=period in (20, 60), required_bars=period)
        for period in (5, 10, 20, 60, 120, 240)
    ),
    *(
        _spec(f"ema{period}", f"EMA{period}", "ema", "overlay", f"近 {period} 根收盤價指數平均，種子為前 {period} 根 SMA。", required_bars=period)
        for period in (5, 12, 26, 50, 200)
    ),
    *(
        _spec(f"ma{period}_slope", f"MA{period} 斜率", "ma_state", "value", f"MA{period} 近 5 根的變化百分比。", required_bars=period + 5)
        for period in (5, 10, 20, 60, 120, 240)
    ),
    *(
        _spec(f"price_to_ma{period}", f"股價距 MA{period}", "ma_state", "value", f"收盤價相對 MA{period} 的乖離百分比。", required_bars=period)
        for period in (5, 10, 20, 60, 120, 240)
    ),
    _spec("bull_alignment", "多頭排列", "ma_state", "flag", "MA5 > MA20 > MA60。", required_bars=60),
    _spec("bear_alignment", "空頭排列", "ma_state", "flag", "MA5 < MA20 < MA60。", required_bars=60),
    _spec("golden_cross", "黃金交叉 MA20xMA60", "ma_state", "flag", "MA20 由下往上穿越 MA60。", required_bars=61),
    _spec("death_cross", "死亡交叉 MA20xMA60", "ma_state", "flag", "MA20 由上往下跌破 MA60。", required_bars=61),
    _spec("golden_cross_short", "短線黃金交叉 MA5xMA20", "ma_state", "flag", "MA5 由下往上穿越 MA20。", required_bars=21),
    _spec("death_cross_short", "短線死亡交叉 MA5xMA20", "ma_state", "flag", "MA5 由上往下跌破 MA20。", required_bars=21),
    _spec("gap_up", "向上缺口", "gap", "flag", "今日最低高於前一日最高。", required_bars=2),
    _spec("gap_down", "向下缺口", "gap", "flag", "今日最高低於前一日最低。", required_bars=2),
    _spec("gap_percent", "開盤缺口幅度", "gap", "value", "今日開盤相對前一日收盤的百分比。", required_bars=2),
    _spec("gap_fill_5d", "5日內回補缺口", "gap", "flag", "缺口後 5 個交易日內是否回補至前收。", required_bars=7),
    _spec("gap_fill_days_5d", "缺口回補天數", "gap", "value", "5 日觀察窗內回補缺口所需交易日。", required_bars=7),
    *(
        _spec(f"momentum_{period}", f"{period}日動能", "momentum", "value", f"收盤價減 {period} 個交易日前收盤。", required_bars=period + 1)
        for period in (5, 10, 20)
    ),
    *(
        _spec(f"roc_{period}", f"{period}日 ROC", "momentum", "value", f"收盤價相對 {period} 個交易日前的變化百分比。", required_bars=period + 1)
        for period in (5, 10, 20)
    ),
    _spec("price_acceleration", "價格加速度", "momentum", "value", "今日 ROC5 減前一日 ROC5。", required_bars=7),
    _spec("daily_range", "日內價差", "volatility", "value", "最高價減最低價。"),
    _spec("daily_range_percent", "日內震幅", "volatility", "value", "日內價差除以前一日收盤。", required_bars=2),
    _spec("tr", "真實波幅 TR", "volatility", "value", "高低價差、最高到前收、最低到前收三者最大值。", required_bars=2),
    *(
        _spec(f"atr_{period}", f"ATR{period}", "volatility", "subplot", f"Wilder 平滑的 {period} 日平均真實波幅。", required_bars=period + 1)
        for period in (5, 14, 20)
    ),
    *(
        _spec(f"hv_{period}", f"HV{period}", "volatility", "subplot", f"{period} 日對數報酬年化波動率。", required_bars=period + 1)
        for period in (20, 60, 120)
    ),
    _spec("annualized_volatility", "年化波動度", "volatility", "value", "同 HV20。", required_bars=21),
    *(
        _spec(f"volume_ma{period}", f"量均{period}", "volume", "subplot", f"近 {period} 日成交量平均。", default_enabled=period == 20, required_bars=period)
        for period in (5, 20, 60)
    ),
    _spec("volume_ratio", "量比", "volume", "value", "成交量除以近 20 日均量。", required_bars=20),
    _spec("volume_spike", "爆量", "volume", "flag", "量比大於等於 2。", required_bars=20),
    _spec("new_volume_high_20", "20日量新高", "volume", "flag", "成交量創近 20 日新高。", required_bars=20),
    _spec("new_volume_low_20", "20日量新低", "volume", "flag", "成交量創近 20 日新低。", required_bars=20),
    _spec("price_up_volume_up", "價漲量增", "volume_price", "flag", "收盤上漲且成交量高於前一日。", required_bars=2),
    _spec("price_up_volume_down", "價漲量縮", "volume_price", "flag", "收盤上漲且成交量低於前一日。", required_bars=2),
    _spec("price_down_volume_up", "價跌量增", "volume_price", "flag", "收盤下跌且成交量高於前一日。", required_bars=2),
    _spec("price_down_volume_down", "價跌量縮", "volume_price", "flag", "收盤下跌且成交量低於前一日。", required_bars=2),
    _spec("obv", "OBV", "volume_price", "subplot", "漲日加量、跌日扣量、平盤不變。", required_bars=2),
    _spec("volume_trend", "OBV 趨勢", "volume_price", "value", "OBV 近 5 根均線斜率。", required_bars=25),
    *(
        _spec(f"high_{period}", f"{period}日高", "rolling_sr", "overlay", f"近 {period} 日最高價。", required_bars=period)
        for period in (20, 60, 120, 250)
    ),
    *(
        _spec(f"low_{period}", f"{period}日低", "rolling_sr", "overlay", f"近 {period} 日最低價。", required_bars=period)
        for period in (20, 60, 120, 250)
    ),
    *(
        _spec(f"distance_to_high_{period}", f"距{period}日高", "rolling_sr", "value", f"收盤相對近 {period} 日高點的距離。", required_bars=period)
        for period in (20, 60, 120, 250)
    ),
    *(
        _spec(f"distance_to_low_{period}", f"距{period}日低", "rolling_sr", "value", f"收盤相對近 {period} 日低點的距離。", required_bars=period)
        for period in (20, 60, 120, 250)
    ),
    _spec("distance_to_52w_high", "距52週高", "rolling_sr", "value", "同距 250 日高。", required_bars=250),
    _spec("distance_to_52w_low", "距52週低", "rolling_sr", "value", "同距 250 日低。", required_bars=250),
    *(
        _spec(f"breakout_{period}", f"突破{period}日前高", "breakout", "flag", f"收盤突破前 {period} 根最高價，不含今日。", required_bars=period + 1)
        for period in (20, 60, 120)
    ),
    *(
        _spec(f"breakdown_{period}", f"跌破{period}日前低", "breakout", "flag", f"收盤跌破前 {period} 根最低價，不含今日。", required_bars=period + 1)
        for period in (20, 60, 120)
    ),
    *(
        _spec(f"breakout_strength_{period}", f"突破{period}日強度", "breakout", "value", f"收盤相對前 {period} 根高點的百分比。", required_bars=period + 1)
        for period in (20, 60, 120)
    ),
    *(
        _spec(f"rsi_{period}", f"RSI{period}", "rsi", "subplot", f"Wilder {period} 日 RSI。", required_bars=period + 1)
        for period in (6, 12, 14, 24)
    ),
    _spec("macd", "MACD DIF", "macd", "subplot", "EMA12 - EMA26。", required_bars=26),
    _spec("macd_signal", "MACD Signal", "macd", "subplot", "DIF 的 EMA9。", required_bars=34),
    _spec("macd_histogram", "MACD 柱", "macd", "subplot", "DIF - Signal。", required_bars=34),
    _spec("macd_golden_cross", "MACD 金叉", "macd", "flag", "DIF 由下往上穿越 Signal。", required_bars=35),
    _spec("macd_dead_cross", "MACD 死叉", "macd", "flag", "DIF 由上往下跌破 Signal。", required_bars=35),
    _spec("kd_k", "K值", "kd", "subplot", "台股常用 9 日 KD 的 K 值。", required_bars=9),
    _spec("kd_d", "D值", "kd", "subplot", "台股常用 9 日 KD 的 D 值。", required_bars=9),
    _spec("kd_j", "J值", "kd", "subplot", "3K - 2D。", required_bars=9),
    _spec("kd_golden_cross", "KD 金叉", "kd", "flag", "K 由下往上穿越 D。", required_bars=10),
    _spec("kd_dead_cross", "KD 死叉", "kd", "flag", "K 由上往下跌破 D。", required_bars=10),
    _spec("bb_middle", "布林中線", "bollinger", "overlay", "MA20。", required_bars=20),
    _spec("bb_upper", "布林上緣", "bollinger", "overlay", "MA20 + 2 個標準差。", required_bars=20),
    _spec("bb_lower", "布林下緣", "bollinger", "overlay", "MA20 - 2 個標準差。", required_bars=20),
    _spec("bb_width", "布林寬度", "bollinger", "value", "(上緣 - 下緣) / 中線。", required_bars=20),
    _spec("bb_position", "布林位置", "bollinger", "value", "收盤在布林上下緣之間的位置。", required_bars=20),
    _spec("bb_squeeze", "布林收斂", "bollinger", "flag", "布林寬度位於近 120 日低檔。", required_bars=139),
    _spec("bb_breakout", "布林突破", "bollinger", "flag", "收盤突破布林上緣或下緣。", required_bars=20),
    _spec("trend_direction", "趨勢方向", "trend", "value", "由均線排列與 MA60 斜率整理為多/空/盤整。", required_bars=65, risk_level=2),
    _spec("trend_strength", "趨勢強度 ADX14", "trend", "subplot", "標準 ADX(14)，描述趨勢強弱。", required_bars=28, risk_level=2),
    _spec("trend_duration", "趨勢延續天數", "trend", "value", "同一趨勢方向連續交易日數。", required_bars=65, risk_level=2),
    _spec("higher_high", "高點墊高", "trend", "flag", "最近兩個樞紐高點是否墊高。", required_bars=30, risk_level=2),
    _spec("higher_low", "低點墊高", "trend", "flag", "最近兩個樞紐低點是否墊高。", required_bars=30, risk_level=2),
    _spec("lower_high", "高點降低", "trend", "flag", "最近兩個樞紐高點是否降低。", required_bars=30, risk_level=2),
    _spec("lower_low", "低點降低", "trend", "flag", "最近兩個樞紐低點是否降低。", required_bars=30, risk_level=2),
    *(
        _spec(key, label, "patterns", "pattern", "自動型態辨識，低信心，僅供參考。", default_enabled=False, required_bars=80, risk_level=3)
        for key, label in (
            ("double_top", "雙重頂"),
            ("double_bottom", "雙重底"),
            ("head_and_shoulders", "頭肩頂"),
            ("inverse_head_and_shoulders", "反頭肩"),
            ("triangle", "三角收斂"),
            ("ascending_triangle", "上升三角"),
            ("descending_triangle", "下降三角"),
            ("flag", "旗形"),
            ("pennant", "三角旗形"),
            ("cup_and_handle", "杯柄"),
        )
    ),
    *(
        _spec(key, label, "scores", "score", "透明加權的目前型態強弱分數，非機率、不預測。", default_enabled=False, required_bars=80, risk_level=4)
        for key, label in (
            ("momentum_score", "動能分數"),
            ("breakout_setup_score", "突破準備分數"),
            ("mean_reversion_score", "均值回歸分數"),
            ("institutional_accumulation_score", "量價累積分數"),
            ("crash_risk_score", "急跌風險分數"),
        )
    ),
)


FEATURES_BY_KEY: dict[str, IndicatorSpec] = {spec.key: spec for spec in FEATURE_SPECS}


PRESETS: dict[str, dict[str, object]] = {
    "newbie": {
        "label": "新手",
        "description": "只顯示最常用的中短期均線，降低畫面噪音。",
        "enabled": ["ma20", "ma60"],
    },
    "technical": {
        "label": "技術派",
        "description": "開啟目前已完成的第 1 層事實型指標。",
        "enabled": [spec.key for spec in FEATURE_SPECS if spec.risk_level == 1],
    },
    "all": {
        "label": "全部",
        "description": "開啟所有登錄指標；高風險層未來仍會附免責。",
        "enabled": [spec.key for spec in FEATURE_SPECS],
    },
    "custom": {
        "label": "自訂",
        "description": "保留使用者自行調整的指標組合。",
        "enabled": [],
    },
}


def indicator_catalog() -> dict[str, object]:
    return {
        "version": 1,
        "categories": [
            {"key": key, "label": label}
            for key, label in CATEGORY_ORDER
        ],
        "features": [asdict(spec) for spec in FEATURE_SPECS],
        "presets": PRESETS,
        "risk_note": "第 1 層為事實型技術讀數；型態與評分層未來預設關閉並加免責。",
    }
