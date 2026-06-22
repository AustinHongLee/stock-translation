from __future__ import annotations

import re
from collections.abc import Iterable


MAX_SYNC_BATCH_TARGETS = 20
_STOCK_ID_PATTERN = re.compile(r"^[0-9A-Za-z]{2,12}$")


def normalize_sync_targets(raw_targets: object, *, max_targets: int = MAX_SYNC_BATCH_TARGETS) -> list[str]:
    """Return a de-duplicated, validated stock-id list for targeted batch sync."""
    targets: list[str]
    if isinstance(raw_targets, str):
        targets = [part.strip() for part in re.split(r"[\s,，、]+", raw_targets)]
    elif isinstance(raw_targets, Iterable):
        targets = [str(part).strip() for part in raw_targets]
    else:
        targets = []

    normalized: list[str] = []
    seen: set[str] = set()
    invalid: list[str] = []
    for target in targets:
        if not target:
            continue
        if not _STOCK_ID_PATTERN.fullmatch(target):
            invalid.append(target)
            continue
        key = target.upper()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(target)

    if invalid:
        raise ValueError(f"invalid stock_id: {invalid[0]}")
    if not normalized:
        raise ValueError("stock_ids is required")
    if len(normalized) > max_targets:
        raise ValueError(f"too many stock_ids; max {max_targets}")
    return normalized
