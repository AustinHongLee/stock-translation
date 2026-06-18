from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.runtime_paths import data_path

DEFAULT_CATALOG_PATH = data_path("stock_catalog.json")


@dataclass(frozen=True, slots=True)
class StockCatalogEntry:
    stock_id: str
    name: str
    short_name: str
    market: str = "TWSE"


def load_stock_catalog(path: Path = DEFAULT_CATALOG_PATH) -> list[StockCatalogEntry]:
    if not path.is_file():
        return []
    stat = path.stat()
    return _load_stock_catalog_cached(str(path), stat.st_mtime_ns)


def search_stock_catalog(
    query: str,
    *,
    limit: int = 20,
    path: Path = DEFAULT_CATALOG_PATH,
) -> list[StockCatalogEntry]:
    normalized_query = _normalize(query)
    if not normalized_query:
        return []

    scored: list[tuple[int, int, StockCatalogEntry]] = []
    for index, entry in enumerate(load_stock_catalog(path)):
        score = _score_entry(entry, normalized_query)
        if score is not None:
            scored.append((score, index, entry))

    scored.sort(key=lambda item: (item[0], item[1]))
    return [entry for _, _, entry in scored[:limit]]


def catalog_has_stock(stock_id: str, path: Path = DEFAULT_CATALOG_PATH) -> bool:
    normalized_id = _normalize(stock_id)
    return any(_normalize(item.stock_id) == normalized_id for item in load_stock_catalog(path))


@lru_cache(maxsize=8)
def _load_stock_catalog_cached(path_text: str, _mtime_ns: int) -> list[StockCatalogEntry]:
    raw = json.loads(Path(path_text).read_text(encoding="utf-8"))
    items = raw.get("items", [])
    catalog: list[StockCatalogEntry] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        stock_id = str(item.get("stock_id", "")).strip()
        name = str(item.get("name", "")).strip()
        short_name = str(item.get("short_name") or name).strip()
        market = str(item.get("market") or "TWSE").strip()
        if stock_id and name:
            catalog.append(
                StockCatalogEntry(
                    stock_id=stock_id,
                    name=name,
                    short_name=short_name,
                    market=market,
                )
            )
    return catalog


def _score_entry(entry: StockCatalogEntry, query: str) -> int | None:
    stock_id = _normalize(entry.stock_id)
    name = _normalize(entry.name)
    short_name = _normalize(entry.short_name)
    haystacks = [stock_id, short_name, name]

    if query == stock_id:
        return 0
    if stock_id.startswith(query):
        return 10 + len(stock_id) - len(query)
    if query in {short_name, name}:
        return 20
    if short_name.startswith(query) or name.startswith(query):
        return 30

    containing_scores = [
        50 + haystack.index(query)
        for haystack in haystacks
        if query in haystack
    ]
    if containing_scores:
        return min(containing_scores)

    if len(query) >= 2:
        combined = f"{stock_id}{short_name}{name}"
        if _is_subsequence(query, combined):
            return 90 + len(combined)
        overlap = _char_overlap(query, combined)
        if overlap >= min(len(query), 2):
            return 130 + (len(query) - overlap) * 10 + len(combined)

    return None


def _normalize(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value)).strip().lower().replace(" ", "")


def _is_subsequence(needle: str, haystack: str) -> bool:
    position = 0
    for char in haystack:
        if position < len(needle) and needle[position] == char:
            position += 1
    return position == len(needle)


def _char_overlap(needle: str, haystack: str) -> int:
    remaining = list(haystack)
    matched = 0
    for char in needle:
        try:
            index = remaining.index(char)
        except ValueError:
            continue
        matched += 1
        remaining.pop(index)
    return matched
