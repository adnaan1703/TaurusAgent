from __future__ import annotations

from typing import Protocol

from taurus_core.intelligence.documents import NewsEvent, RawDocument


class DocumentProvider(Protocol):
    def list_documents(self) -> list[RawDocument]:
        ...


class NewsProvider(DocumentProvider, Protocol):
    def list_events(self) -> list[NewsEvent]:
        ...
