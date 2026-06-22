from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

GLOSSARY_PATH = Path(__file__).with_name("terms.json")
DEFAULT_REMINDER = "這是名詞解釋，只能幫助閱讀資料，不是買賣建議，也不預測股價。"


@dataclass(frozen=True, slots=True)
class GlossaryEntry:
    term: str
    aliases: tuple[str, ...]
    plain: str
    how_to_read: str
    reminder: str

    def to_json(self) -> dict[str, object]:
        return {
            "term": self.term,
            "aliases": list(self.aliases),
            "plain": self.plain,
            "how_to_read": self.how_to_read,
            "reminder": self.reminder,
        }


@lru_cache(maxsize=1)
def load_glossary() -> tuple[GlossaryEntry, ...]:
    raw = json.loads(GLOSSARY_PATH.read_text(encoding="utf-8"))
    return tuple(
        GlossaryEntry(
            term=str(item["term"]),
            aliases=tuple(str(alias) for alias in item.get("aliases", [])),
            plain=str(item["plain"]),
            how_to_read=str(item["how_to_read"]),
            reminder=str(item.get("reminder") or DEFAULT_REMINDER),
        )
        for item in raw
    )


def glossary_payload() -> dict[str, object]:
    entries = load_glossary()
    return {
        "entries": [entry.to_json() for entry in entries],
        "aliases": _alias_map(entries),
    }


def _alias_map(entries: tuple[GlossaryEntry, ...]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for entry in entries:
        aliases[entry.term] = entry.term
        for alias in entry.aliases:
            aliases[alias] = entry.term
    return aliases
