"""
Tiny wrapper over the Paperless-ngx REST API.

Phase 2 uses this to fetch OCR'd document text. The worker calls
`get_document_text(paperless_id)` once per new document and feeds the
returned content into the extractor registry.

Configuration comes from .env: `PAPERLESS_URL_PUBLIC` for the base URL,
`PAPERLESS_API_TOKEN` for the bearer token. Both are loaded by the
worker's `load_dotenv(override=True)` call before this module is exercised.

Errors propagate as `requests.HTTPError` (network / 4xx / 5xx) or
`RuntimeError` (missing env). The worker treats any exception during
`run_one_pass` as a transient failure, logs it, and tries again next
poll cycle.
"""

from __future__ import annotations

import os
from typing import Any

import requests

_DEFAULT_TIMEOUT = 30


def _base_url() -> str:
    url = os.environ.get("PAPERLESS_URL_PUBLIC")
    if not url:
        raise RuntimeError("PAPERLESS_URL_PUBLIC not set in environment")
    return url.rstrip("/")


def _headers() -> dict[str, str]:
    token = os.environ.get("PAPERLESS_API_TOKEN")
    if not token:
        raise RuntimeError("PAPERLESS_API_TOKEN not set in environment")
    return {"Authorization": f"Token {token}"}


def get_document_text(paperless_id: int) -> str:
    """Return the OCR'd content body of the document."""
    url = f"{_base_url()}/api/documents/{paperless_id}/?fields=content"
    resp = requests.get(url, headers=_headers(), timeout=_DEFAULT_TIMEOUT)
    resp.raise_for_status()
    return resp.json().get("content", "") or ""


def get_document(paperless_id: int) -> dict[str, Any]:
    """Return full document metadata for the given Paperless document ID."""
    url = f"{_base_url()}/api/documents/{paperless_id}/"
    resp = requests.get(url, headers=_headers(), timeout=_DEFAULT_TIMEOUT)
    resp.raise_for_status()
    return resp.json()
