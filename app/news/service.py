"""個股新聞抓取與規則式歸類（L1）。

定位（對齊《09》8.2 `news/` 與工作流 D）：
- 只抓**公開新聞 RSS**，送出的查詢只有「股票代號＋名稱」這種公開資訊，
  不送任何持倉/個人資料（隱私紅線 R9）。
- 多來源互補：Google News + 第二來源（Bing News）+ 事件導向查詢，合併後依標題去重。
  （Yahoo 奇摩股市目前未提供官方「個股 RSS」公開端點；多來源架構已備好，
  日後若有可用的 Yahoo 端點，只要在 NEWS_SOURCES 加一行即可。）
- 每則新聞用 `classifier`（純規則、加權關鍵字）標利多/利空/中性，並標事件類型，
  **不接 AI、不預測股價、不報明牌**。抓取為「開個股頁時即時抓」，有逾時與降級。
"""
from __future__ import annotations

import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable
from urllib.parse import quote_plus

from app.news.classifier import (
    LABEL_NEGATIVE,
    LABEL_NEUTRAL,
    LABEL_POSITIVE,
    build_overall_sentence,
    classify_headline,
    detect_events,
)
from app.news.risk_matrix import build_risk_summary, rolling_risk, score_news

NEWS_DISCLAIMER = "消息整理為多來源公開新聞的關鍵字歸類，僅供快速了解，非投資建議、不預測股價。"
_USER_AGENT = "Mozilla/5.0 (compatible; StockTranslator/1.0; +local)"
EVENT_LOOKBACK_DAYS = 45
EVENT_QUERY_TERMS: tuple[str, ...] = (
    "重大訊息", "重訊", "暫停交易", "變更交易方法", "分盤集合競價", "終止上市", "下市", "下櫃",
    "淨值", "全額交割", "重整", "違約", "調解", "訴訟", "裁罰", "資產處分", "私募", "增資",
    "併購", "法說", "財測", "得標", "大單", "工安", "停工",
)

Fetcher = Callable[[str, float], bytes]


def _keyword(stock_id: str, name: str) -> str:
    return " ".join(part for part in [str(stock_id or "").strip(), str(name or "").strip()] if part)


def google_news_rss_url(stock_id: str, name: str, *, days: int = 14) -> str:
    """組 Google News RSS 查詢網址（繁中、台灣）。"""
    keyword = _keyword(stock_id, name)
    query = f'"{keyword}" 股票 when:{days}d' if keyword else f"台股 when:{days}d"
    return (
        "https://news.google.com/rss/search?q="
        + quote_plus(query)
        + "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    )


def bing_news_rss_url(stock_id: str, name: str, *, days: int = 14) -> str:
    """組 Bing News RSS 查詢網址（繁中、台灣）作為互補第二來源。"""
    keyword = _keyword(stock_id, name) or "台股"
    return (
        "https://www.bing.com/news/search?q="
        + quote_plus(f"{keyword} 股票")
        + "&format=RSS&setlang=zh-hant&cc=TW"
    )


def google_events_rss_url(stock_id: str, name: str, *, days: int = 30) -> str:
    """事件導向查詢：偏重併購/法說/擴廠/財測/重訊等『公司動向』，補一般新聞較少抓到的大事。"""
    keyword = _keyword(stock_id, name)
    if not keyword:
        return google_news_rss_url(stock_id, name, days=days)
    event_days = max(days, EVENT_LOOKBACK_DAYS)
    event_query = " OR ".join(EVENT_QUERY_TERMS)
    query = (
        f'"{keyword}" ({event_query}) '
        f"when:{event_days}d"
    )
    return (
        "https://news.google.com/rss/search?q="
        + quote_plus(query)
        + "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    )


# 來源清單：(顯示名稱, 網址產生器)。要加 Yahoo 等來源，在此加一行即可。
NEWS_SOURCES: tuple[tuple[str, Callable[..., str]], ...] = (
    ("Google News", google_news_rss_url),
    ("Bing News", bing_news_rss_url),
    ("Google 事件", google_events_rss_url),
)


def _default_fetch(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (公開 RSS)
        return response.read()


def fetch_company_news(
    stock_id: str,
    name: str = "",
    *,
    days: int = 14,
    limit: int = 10,
    timeout: float = 6.0,
    fetch: Fetcher | None = None,
    sources: tuple[tuple[str, Callable[..., str]], ...] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    """從多個來源抓取並歸類個股新聞；任何來源失敗都跳過，全失敗才降級。"""
    fetcher = fetch or _default_fetch
    used_sources = sources or NEWS_SOURCES
    collected: list[dict[str, str]] = []
    source_status: dict[str, str] = {}
    last_url = ""
    for source_name, url_builder in used_sources:
        url = url_builder(stock_id, name, days=days)
        last_url = url
        try:
            raw = fetcher(url, timeout)
            parsed = _parse_rss_items(raw, limit=limit * 2, source_name=source_name)
            collected.extend(parsed)
            source_status[source_name] = "ok"
        except Exception as exc:  # noqa: BLE001 - 單一來源失敗不影響其他
            source_status[source_name] = f"failed: {exc}"

    if not collected and all(status != "ok" for status in source_status.values()):
        return _unavailable(stock_id, name, days, last_url, source_status, generated_at)

    return _assemble_payload(
        stock_id,
        name,
        collected,
        days=days,
        limit=limit,
        query_url=last_url,
        source_status=source_status,
        generated_at=generated_at,
    )


def build_news_payload(
    stock_id: str,
    name: str,
    raw_xml: bytes | str,
    *,
    days: int = 14,
    limit: int = 10,
    query_url: str = "",
    generated_at: datetime | None = None,
) -> dict[str, object]:
    """純解析 + 歸類（單一來源 RSS 內容），可單元測試、不碰網路。"""
    items = _parse_rss_items(raw_xml, limit=limit, source_name="")
    return _assemble_payload(
        stock_id,
        name,
        items,
        days=days,
        limit=limit,
        query_url=query_url,
        source_status={},
        generated_at=generated_at,
    )


def overall_label(positive: int, negative: int, neutral: int) -> str:
    """單字傾向標籤，給第一層『消息溫度計』晶片用。"""
    total = positive + negative + neutral
    if total == 0:
        return "無消息"
    if positive > negative and positive >= max(1, total * 0.4):
        return "偏多"
    if negative > positive and negative >= max(1, total * 0.4):
        return "偏空"
    return "中性"


def _assemble_payload(
    stock_id: str,
    name: str,
    raw_items: list[dict[str, str]],
    *,
    days: int,
    limit: int,
    query_url: str,
    source_status: dict[str, str],
    generated_at: datetime | None,
) -> dict[str, object]:
    items = _dedupe_by_title(raw_items)[: max(0, limit)]
    counts = {LABEL_POSITIVE: 0, LABEL_NEGATIVE: 0, LABEL_NEUTRAL: 0}
    enriched: list[dict[str, object]] = []
    item_risks: list[dict[str, object]] = []
    dated_scores: list[tuple[date, int]] = []
    for item in items:
        verdict = classify_headline(item["title"])
        counts[verdict.label] += 1
        risk = score_news(item["title"])
        item_risks.append(risk)
        published = _to_date(item.get("published"))
        if published is not None:
            dated_scores.append((published, int(risk["risk_score"])))
        enriched.append(
            {
                "title": item["title"],
                "link": item["link"],
                "source": item["source"],
                "provider": item.get("provider", ""),
                "published": item["published"],
                "label": verdict.label,
                "reason": verdict.reason,
                "events": detect_events(item["title"]),
                "risk": risk,
            }
        )

    generated = generated_at or datetime.now(timezone.utc)
    risk_summary = build_risk_summary(item_risks)
    windows = rolling_risk(dated_scores, generated.date())
    risk_summary["windows"] = {"d7": windows["d7"], "d14": windows["d14"], "d45": windows["d45"]}
    risk_summary["heating"] = windows["heating"]
    if windows["heating"]:
        risk_summary.setdefault("reasons", []).append("近 7 天風險詞明顯增加（風險升溫）。")

    pos, neg, neu = counts[LABEL_POSITIVE], counts[LABEL_NEGATIVE], counts[LABEL_NEUTRAL]
    return {
        "status": "available" if enriched else "empty",
        "stock_id": stock_id,
        "name": name,
        "days": days,
        "query_url": query_url,
        "generated_at": generated.isoformat(timespec="seconds"),
        "overall": build_overall_sentence(positive=pos, negative=neg, neutral=neu, days=days),
        "overall_label": overall_label(pos, neg, neu),
        "counts": counts,
        "top": _top_headlines(enriched),
        "recent_events": _recent_events(enriched),
        "risk_summary": risk_summary,
        "sources": source_status,
        "items": enriched,
        "disclaimer": NEWS_DISCLAIMER,
    }


def _to_date(value: object) -> date | None:
    text = str(value or "").strip()
    if len(text) >= 10:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
    return None


def _recent_events(items: list[dict[str, object]]) -> list[str]:
    """近期出現的事件類型（依出現次數排序），給『近期動向』摘要用。"""
    counts: dict[str, int] = {}
    for item in items:
        for event in item.get("events") or []:
            counts[event] = counts.get(event, 0) + 1
    return [event for event, _ in sorted(counts.items(), key=lambda kv: -kv[1])][:5]


def _top_headlines(items: list[dict[str, object]], k: int = 2) -> list[dict[str, object]]:
    """挑出最具代表性的幾則（優先有明確傾向者），給第一層摘要用。"""
    signalled = [item for item in items if item.get("label") != LABEL_NEUTRAL]
    chosen = (signalled or items)[:k]
    return [{"title": item["title"], "label": item["label"], "link": item.get("link", "")} for item in chosen]


def _unavailable(
    stock_id: str,
    name: str,
    days: int,
    url: str,
    source_status: dict[str, str],
    generated_at: datetime | None,
) -> dict[str, object]:
    return {
        "status": "unavailable",
        "stock_id": stock_id,
        "name": name,
        "days": days,
        "query_url": url,
        "generated_at": (generated_at or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "overall": "目前無法取得新聞（可能是沒有網路或來源暫時無回應），稍後再試。",
        "overall_label": "無消息",
        "counts": {LABEL_POSITIVE: 0, LABEL_NEGATIVE: 0, LABEL_NEUTRAL: 0},
        "top": [],
        "recent_events": [],
        "risk_summary": {
            "score": 0, "level": "無", "top_dimensions": [], "reasons": [],
            "windows": {"d7": 0, "d14": 0, "d45": 0}, "heating": False,
        },
        "sources": source_status,
        "items": [],
        "disclaimer": NEWS_DISCLAIMER,
    }


def _dedupe_by_title(items: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for item in items:
        key = _normalize_title(item.get("title", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _normalize_title(title: str) -> str:
    text = str(title or "").strip().lower()
    for ch in " 　,，。.、!！?？「」『』()（）-—｜|":
        text = text.replace(ch, "")
    return text


def _parse_rss_items(raw_xml: bytes | str, *, limit: int, source_name: str = "") -> list[dict[str, str]]:
    root = ET.fromstring(raw_xml)
    channel = root.find("channel")
    nodes = channel.findall("item") if channel is not None else root.findall(".//item")
    results: list[dict[str, str]] = []
    for node in nodes[: max(0, limit)]:
        raw_title = (node.findtext("title") or "").strip()
        if not raw_title:
            continue
        media = (node.findtext("source") or "").strip()
        title = raw_title
        # 聚合器標題常為「標題 - 媒體」；沒有 <source> 時從尾端切出媒體名。
        if not media and " - " in raw_title:
            title, _, media = raw_title.rpartition(" - ")
            title = title.strip()
            media = media.strip()
        results.append(
            {
                "title": title or raw_title,
                "link": (node.findtext("link") or "").strip(),
                "source": media or source_name,
                "provider": source_name,
                "published": _format_published(node.findtext("pubDate")),
            }
        )
    return results


def _format_published(raw: str | None) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    try:
        return parsedate_to_datetime(value).astimezone().strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return value
