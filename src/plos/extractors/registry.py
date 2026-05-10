"""
Graduated-extractor registry and dispatcher.

A graduated extractor is a deterministic, free, local parser for a
recurring document type. Each is a callable matching:

    def extract(text: str, document: DocumentMeta) -> dict[str, Any] | None

It returns a dict of field updates if it recognizes the document, or
None to pass. `dispatch` tries each registered extractor in order and
returns the first non-None result paired with that extractor's handler
name (which lands in `extracted_fields.handler` for audit).

The active list of extractors is intentionally a small explicit list at
the bottom of this module — no auto-discovery, no plugin metaclass, no
import-time side effects in the extractor modules themselves. Adding a
new extractor is one import + one tuple entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class DocumentMeta:
    """Lightweight bundle the worker passes to each extractor.

    Carries only what extractors need: the Paperless ID and URL (used to
    record provenance), the document's effective date (for freshness
    reasoning), and the correspondent (for fast matching before parsing).
    """

    paperless_id: int
    paperless_url: str
    document_date: date | None
    correspondent: str | None


ExtractorFn = Callable[[str, DocumentMeta], Optional[dict[str, Any]]]


from plos.extractors.graduated import utility_bill_electric  # noqa: E402

# Active graduated extractors, in dispatch order. Adding a new extractor
# is one import + one tuple entry. Tests that need a specific registry
# state patch this list via monkeypatch.setattr.
EXTRACTORS: list[tuple[str, ExtractorFn]] = [
    ("graduated:utility_bill_electric", utility_bill_electric.extract),
]


def dispatch(text: str, document: DocumentMeta) -> tuple[str, dict[str, Any]] | None:
    """Try each registered extractor; return (handler_name, fields) for the first match.

    Returns None when no extractor recognized the document — the worker
    treats that as 'route to the AI fallback queue' (status='pending_claude').
    """
    for name, fn in EXTRACTORS:
        result = fn(text, document)
        if result is not None:
            return name, result
    return None
