from __future__ import annotations

from typing import Protocol

from app.models import IntradayQuote
from app.sync.twse import TwseClient


class QuoteProvider(Protocol):
    def fetch_quote(self, stock_id: str) -> IntradayQuote | None:
        """Return the latest available intraday quote for a stock."""


class TwseMisQuoteProvider:
    def __init__(self, client: TwseClient | None = None) -> None:
        self.client = client or TwseClient(timeout=5.0, request_interval=0.0)

    def fetch_quote(self, stock_id: str) -> IntradayQuote | None:
        return self.client.fetch_intraday_quote(stock_id)
