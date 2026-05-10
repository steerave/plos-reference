"""
Graduated-extractor registry and dispatcher.

A graduated extractor is a deterministic, free, local parser for a
recurring document type. Each is a Python module under
`plos.extractors.graduated.*` exporting two callables:

    def extract(text: str, document: DocumentMeta) -> dict[str, Any] | None
    def route(fields: dict[str, Any], vault_root: Path) -> RouteResult

`extract` returns a dict of field updates if the extractor recognizes
the document, or None to pass. `route` takes the extracted fields and
locates the entity record they should be merged into:

  RouteResult(path=Path(...), missing_key=False) — entity matched
  RouteResult(path=None,      missing_key=False) — extracted fields
                                                    are valid but no
                                                    entity in the vault
                                                    matches them
  RouteResult(path=None,      missing_key=True)  — the routing key the
                                                    extractor needs to
                                                    locate an entity
                                                    isn't present in
                                                    `fields` (e.g. an
                                                    Acme bill that
                                                    OCR'd without the
                                                    account number)

The worker dispatches off the result: matched -> merge + done;
unmatched_entity -> needs_review with reason 'unmatched_entity';
missing_key -> needs_review with reason 'no_routing_key_in_extraction'.

The active list of extractors is intentionally a small explicit list at
the bottom of this module — no auto-discovery, no plugin metaclass, no
import-time side effects in the extractor modules themselves. Adding a
new extractor is one import + one tuple entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from types import ModuleType
from typing import Any, NamedTuple


@dataclass(frozen=True)
class DocumentMeta:
    """Lightweight bundle the worker passes to each extractor's `extract`.

    Carries only what extractors need: the Paperless ID and URL (used to
    record provenance), the document's effective date (for freshness
    reasoning), and the correspondent (for fast matching before parsing).
    """

    paperless_id: int
    paperless_url: str
    document_date: date | None
    correspondent: str | None


class RouteResult(NamedTuple):
    """The outcome of an extractor's `route(fields, vault_root)` call."""

    path: Any  # pathlib.Path | None — kept loose to avoid an import here
    missing_key: bool


from plos.extractors.graduated import (  # noqa: E402
    mortgage_statement_mr_cooper,
    utility_bill_electric,
)

# Active graduated extractors, in dispatch order. Adding a new extractor
# is one import + one tuple entry. Tests that need a specific registry
# state patch this list via monkeypatch.setattr.
EXTRACTORS: list[tuple[str, ModuleType]] = [
    ("graduated:utility_bill_electric", utility_bill_electric),
    ("graduated:mortgage_statement_mr_cooper", mortgage_statement_mr_cooper),
]


def dispatch(
    text: str, document: DocumentMeta
) -> tuple[str, ModuleType, dict[str, Any]] | None:
    """Try each registered extractor; return (handler, module, fields) for the first match.

    Returns None when no extractor recognized the document — the worker
    treats that as 'route to the AI fallback queue' (status='pending_claude').
    The worker uses the returned `module` to call `module.route(...)` and
    locate the entity to merge into.
    """
    for name, module in EXTRACTORS:
        result = module.extract(text, document)
        if result is not None:
            return name, module, result
    return None
