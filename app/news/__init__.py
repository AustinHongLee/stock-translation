"""新聞模組：公開 RSS 抓取 + 規則式利多/利空/中性歸類 + 事件類型標籤（不接 AI、不預測股價）。"""
from app.news.classifier import (
    EVENT_KEYWORDS,
    LABEL_NEGATIVE,
    LABEL_NEUTRAL,
    LABEL_POSITIVE,
    HeadlineVerdict,
    classify_headline,
    contains_forbidden,
    detect_events,
    load_lexicon,
)
from app.news.service import (
    NEWS_DISCLAIMER,
    NEWS_SOURCES,
    bing_news_rss_url,
    build_news_payload,
    fetch_company_news,
    google_events_rss_url,
    google_news_rss_url,
    overall_label,
)

__all__ = [
    "LABEL_POSITIVE",
    "LABEL_NEGATIVE",
    "LABEL_NEUTRAL",
    "EVENT_KEYWORDS",
    "HeadlineVerdict",
    "classify_headline",
    "contains_forbidden",
    "detect_events",
    "load_lexicon",
    "NEWS_DISCLAIMER",
    "NEWS_SOURCES",
    "bing_news_rss_url",
    "build_news_payload",
    "fetch_company_news",
    "google_events_rss_url",
    "google_news_rss_url",
    "overall_label",
]
