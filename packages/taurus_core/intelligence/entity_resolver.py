from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from taurus_core.db.models import InstrumentModel
from taurus_core.domain.instruments import Instrument
from taurus_core.intelligence.documents import RawDocument

LEGAL_SUFFIXES = {"LTD", "LIMITED"}


@dataclass(frozen=True, slots=True)
class ResolvedEntity:
    symbol: str
    name: str
    matched_text: str


class EntityResolver:
    def __init__(self, instruments: Iterable[Instrument | InstrumentModel]) -> None:
        self._by_symbol: dict[str, ResolvedEntity] = {}
        self._alias_to_symbol: dict[str, str] = {}
        for instrument in instruments:
            symbol = instrument.symbol.upper()
            name = instrument.name
            self._by_symbol[symbol] = ResolvedEntity(
                symbol=symbol,
                name=name,
                matched_text=symbol,
            )
            for alias in _aliases(symbol, name):
                self._alias_to_symbol[alias] = symbol

    def resolve_symbol(self, value: str) -> ResolvedEntity | None:
        symbol = self._alias_to_symbol.get(_normalize(value))
        if symbol is None:
            return None
        entity = self._by_symbol[symbol]
        return ResolvedEntity(symbol=entity.symbol, name=entity.name, matched_text=value)

    def resolve_text(self, text: str) -> list[ResolvedEntity]:
        normalized_text = _normalize(text)
        tokens = set(normalized_text.split())
        matches: dict[str, ResolvedEntity] = {}
        for alias, symbol in self._alias_to_symbol.items():
            alias_tokens = alias.split()
            matched = False
            if len(alias_tokens) == 1:
                matched = alias_tokens[0] in tokens
            else:
                matched = f" {alias} " in f" {normalized_text} "
            if matched:
                entity = self._by_symbol[symbol]
                matches[symbol] = ResolvedEntity(
                    symbol=symbol,
                    name=entity.name,
                    matched_text=alias,
                )
        return [matches[symbol] for symbol in sorted(matches)]

    def resolve_document(self, document: RawDocument) -> list[ResolvedEntity]:
        matches: dict[str, ResolvedEntity] = {}
        for value in [*document.symbols, *document.entities]:
            entity = self.resolve_symbol(value)
            if entity is not None:
                matches[entity.symbol] = entity
        for entity in self.resolve_text(f"{document.title}\n{document.body}"):
            matches.setdefault(entity.symbol, entity)
        return [matches[symbol] for symbol in sorted(matches)]


def _aliases(symbol: str, name: str) -> set[str]:
    normalized_name = _normalize(name)
    aliases = {
        _normalize(symbol),
        normalized_name,
        _normalize(name.replace("&", "and")),
        _normalize(name.replace("and", "&")),
    }
    name_without_suffix = " ".join(
        token for token in normalized_name.split() if token not in LEGAL_SUFFIXES
    )
    if name_without_suffix:
        aliases.add(name_without_suffix)
    first_token = name_without_suffix.split()[0] if name_without_suffix else ""
    if len(first_token) >= 4:
        aliases.add(first_token)
    return {alias for alias in aliases if alias}


def _normalize(value: str) -> str:
    value = value.upper().replace("&", " AND ")
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    return " ".join(value.split())
