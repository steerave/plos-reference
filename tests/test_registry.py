"""
Tests for the extractor dispatcher.

Validates ordering and pass-through behavior with mock extractors so
real extractors stay independently testable.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from plos.extractors import registry


@pytest.fixture
def doc():
    return registry.DocumentMeta(
        paperless_id=42,
        paperless_url="http://localhost:8888/documents/42/",
        document_date=date(2026, 4, 30),
        correspondent="Acme Power & Light",
    )


@pytest.fixture(autouse=True)
def _empty_registry(monkeypatch):
    monkeypatch.setattr(registry, "EXTRACTORS", [])


def test_dispatch_returns_none_when_empty(doc):
    assert registry.dispatch("any text", doc) is None


def test_dispatch_returns_none_when_no_match(doc, monkeypatch):
    def never(text, document):
        return None

    monkeypatch.setattr(registry, "EXTRACTORS", [("graduated:never", never)])
    assert registry.dispatch("hi", doc) is None


def test_dispatch_returns_first_match(doc, monkeypatch):
    def first(text: str, document: registry.DocumentMeta) -> dict[str, Any] | None:
        return {"first": True}

    def second(text: str, document: registry.DocumentMeta) -> dict[str, Any] | None:
        return {"second": True}

    monkeypatch.setattr(
        registry,
        "EXTRACTORS",
        [("graduated:first", first), ("graduated:second", second)],
    )
    name, fields = registry.dispatch("anything", doc)
    assert name == "graduated:first"
    assert fields == {"first": True}


def test_dispatch_falls_through_to_next_on_none(doc, monkeypatch):
    def first(text, document):
        return None

    def second(text, document):
        return {"matched": True}

    monkeypatch.setattr(
        registry,
        "EXTRACTORS",
        [("graduated:first", first), ("graduated:second", second)],
    )
    name, fields = registry.dispatch("text", doc)
    assert name == "graduated:second"
    assert fields == {"matched": True}


def test_document_meta_is_immutable(doc):
    """Frozen dataclass — extractors can't sneak mutations back."""
    with pytest.raises((AttributeError, Exception)):
        doc.paperless_id = 99
