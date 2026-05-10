"""
Tests for the Paperless REST client wrapper.

Uses the `responses` library to intercept outbound HTTP. The client is
small enough that contract coverage (URL shape, auth header, response
parsing, env-var validation) is the entire test surface.
"""

from __future__ import annotations

import pytest
import responses
from responses import matchers

from plos import paperless


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("PAPERLESS_URL_PUBLIC", "http://localhost:8888")
    monkeypatch.setenv("PAPERLESS_API_TOKEN", "test-token-abc")


@responses.activate
def test_get_document_text_returns_content():
    responses.add(
        responses.GET,
        "http://localhost:8888/api/documents/42/",
        json={"content": "OCR'd text here"},
        status=200,
        match=[matchers.query_param_matcher({"fields": "content"})],
    )
    assert paperless.get_document_text(42) == "OCR'd text here"


@responses.activate
def test_get_document_text_handles_null_content():
    """Paperless returns content=None for documents that haven't been OCR'd yet."""
    responses.add(
        responses.GET,
        "http://localhost:8888/api/documents/7/",
        json={"content": None},
        status=200,
        match=[matchers.query_param_matcher({"fields": "content"})],
    )
    assert paperless.get_document_text(7) == ""


@responses.activate
def test_get_document_returns_metadata():
    responses.add(
        responses.GET,
        "http://localhost:8888/api/documents/42/",
        json={"id": 42, "title": "Test", "correspondent": 5},
        status=200,
    )
    doc = paperless.get_document(42)
    assert doc["id"] == 42
    assert doc["title"] == "Test"
    assert doc["correspondent"] == 5


@responses.activate
def test_uses_token_auth_header():
    responses.add(
        responses.GET,
        "http://localhost:8888/api/documents/42/",
        json={"content": ""},
        status=200,
        match=[matchers.query_param_matcher({"fields": "content"})],
    )
    paperless.get_document_text(42)
    sent = responses.calls[0].request
    assert sent.headers["Authorization"] == "Token test-token-abc"


@responses.activate
def test_strips_trailing_slash_from_base_url(monkeypatch):
    monkeypatch.setenv("PAPERLESS_URL_PUBLIC", "http://localhost:8888/")
    responses.add(
        responses.GET,
        "http://localhost:8888/api/documents/42/",
        json={"content": "ok"},
        status=200,
        match=[matchers.query_param_matcher({"fields": "content"})],
    )
    assert paperless.get_document_text(42) == "ok"


@responses.activate
def test_4xx_raises():
    responses.add(
        responses.GET,
        "http://localhost:8888/api/documents/999/",
        json={"detail": "Not found."},
        status=404,
        match=[matchers.query_param_matcher({"fields": "content"})],
    )
    with pytest.raises(Exception):  # requests.HTTPError
        paperless.get_document_text(999)


def test_missing_url_raises(monkeypatch):
    monkeypatch.delenv("PAPERLESS_URL_PUBLIC", raising=False)
    with pytest.raises(RuntimeError, match="PAPERLESS_URL_PUBLIC"):
        paperless.get_document_text(42)


def test_missing_token_raises(monkeypatch):
    monkeypatch.delenv("PAPERLESS_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="PAPERLESS_API_TOKEN"):
        paperless.get_document_text(42)
