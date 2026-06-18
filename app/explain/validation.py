from __future__ import annotations

from app.analyze.health import HealthMetrics, calculate_health_metrics
from app.models import DailyPrice


def build_validation_brief(prices: list[DailyPrice]) -> dict[str, object]:
    metrics = calculate_health_metrics(prices)
    return {
        "title": "明牌驗證工作台",
        "items": [
            _trend_item(metrics),
            _position_item(metrics),
            _data_gap_item(),
        ],
    }


def _trend_item(metrics: HealthMetrics) -> dict[str, object]:
    change = metrics.trend.change_20d_percent
    if change is None:
        return {
            "label": "最近趨勢",
            "tone": "unknown",
            "text": "日線資料不足，還不能看短期趨勢。",
        }
    if change >= 5:
        tone = "caution"
        text = f"近 20 個交易日收盤約上升 {change:.2f}%，先留意是不是短期已經漲一段。"
    elif change <= -5:
        tone = "caution"
        text = f"近 20 個交易日收盤約下跌 {abs(change):.2f}%，先留意下跌原因和波動。"
    else:
        tone = "neutral"
        text = f"近 20 個交易日收盤變化約 {change:+.2f}%，短期不是大幅單邊。"
    return {"label": "最近趨勢", "tone": tone, "text": text}


def _position_item(metrics: HealthMetrics) -> dict[str, object]:
    position = metrics.price_position.position
    if position is None:
        return {
            "label": "價格位階",
            "tone": "unknown",
            "text": "價格區間資料不足，還不能看目前位階。",
        }
    percent = position * 100
    if position >= 0.75:
        tone = "caution"
        text = f"目前在近一年區間約 {percent:.0f}% 的位置，已偏高；聽到明牌時要先看風險。"
    elif position <= 0.25:
        tone = "neutral"
        text = f"目前在近一年區間約 {percent:.0f}% 的位置，偏低，但仍要確認公司基本面。"
    else:
        tone = "neutral"
        text = f"目前在近一年區間約 {percent:.0f}% 的位置，價格位置屬於中段。"
    return {"label": "價格位階", "tone": tone, "text": text}


def _data_gap_item() -> dict[str, object]:
    return {
        "label": "還缺什麼",
        "tone": "unknown",
        "text": "目前還沒接營收、EPS、ROE，所以只能驗證價格與波動，還不能判斷公司賺不賺錢。",
    }
