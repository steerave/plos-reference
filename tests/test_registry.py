"""
Tests for the extractor dispatcher.

Validates ordering and pass-through behavior with mock extractor
modules so real extractors stay independently testable. A mock
"module" is just a SimpleNamespace exposing the contract `dispatch`
cares about (`extract`).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from plos.extractors import registry


def _module(extract_fn) -> SimpleNamespace:
    """Build a fake extractor module exposing just the `extract` callable."""
    return SimpleNamespace(extract=extract_fn)


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

    monkeypatch.setattr(
        registry, "EXTRACTORS", [("graduated:never", _module(never))]
    )
    assert registry.dispatch("hi", doc) is None


def test_dispatch_returns_first_match(doc, monkeypatch):
    def first(text: str, document: registry.DocumentMeta) -> dict[str, Any] | None:
        return {"first": True}

    def second(text: str, document: registry.DocumentMeta) -> dict[str, Any] | None:
        return {"second": True}

    first_mod = _module(first)
    monkeypatch.setattr(
        registry,
        "EXTRACTORS",
        [("graduated:first", first_mod), ("graduated:second", _module(second))],
    )
    name, module, fields = registry.dispatch("anything", doc)
    assert name == "graduated:first"
    assert module is first_mod
    assert fields == {"first": True}


def test_dispatch_falls_through_to_next_on_none(doc, monkeypatch):
    def first(text, document):
        return None

    def second(text, document):
        return {"matched": True}

    second_mod = _module(second)
    monkeypatch.setattr(
        registry,
        "EXTRACTORS",
        [("graduated:first", _module(first)), ("graduated:second", second_mod)],
    )
    name, module, fields = registry.dispatch("text", doc)
    assert name == "graduated:second"
    assert module is second_mod
    assert fields == {"matched": True}


def test_document_meta_is_immutable(doc):
    """Frozen dataclass — extractors can't sneak mutations back."""
    with pytest.raises((AttributeError, Exception)):
        doc.paperless_id = 99
