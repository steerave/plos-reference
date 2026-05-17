"""
Audit pass for the v1 compiled artifacts.

Per the design principle in ARCHITECTURE.md / CONVENTIONS.md, every
compiled artifact must cite its sources inline (`→ /source/...`
arrows under each bullet) and declare them in its
`sources_read:` frontmatter list. The audit pass verifies that
contract: for each artifact under `compiled/`, it parses the
frontmatter declaration and the body's arrow citations and flags
drift in three categories:

- **undeclared_citation** — the body cites a path that the
  frontmatter `sources_read:` list doesn't declare. The AI
  synthesized from a source it didn't tell us about.
- **unused_declaration** — the frontmatter `sources_read:` lists
  a path that the body never cites. The AI read but didn't
  surface the result. Mild.
- **nonexistent_citation** — the body cites a path that doesn't
  exist anywhere in the vault. AI path hallucination — highest-
  value finding.

The audit is purely deterministic Python; no Claude involvement.
The audit pass is the meta-layer that keeps the AI-synthesized
artifacts honest.

The report lands at `_review/audit-report.md` (gitignored, same
treatment as `compiled/`). It carries frontmatter declaring the
audit timestamp + counts per category, then a markdown section
per artifact with its findings (or a "clean" marker if the
artifact passed).

Run from the repo root:
    python -m plos.audit_pass
"""

from __future__ import annotations

import logging
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

logger = logging.getLogger("plos.audit_pass")

REPORT_PATH = Path("_review/audit-report.md")
AUDITED_ARTIFACTS = (
    Path("compiled/this-week.md"),
    Path("compiled/anomalies.md"),
    Path("compiled/tax-prep.md"),
)

# Match "→ /<path-without-whitespace>" anywhere in the body. The arrow
# character is U+2192. We capture the leading-slash path up to the next
# whitespace; trailing punctuation that's not part of a path is rare in
# the compile-pass output (templates use the path as its own line) and
# would be a finding worth flagging anyway.
_ARROW_RE = re.compile(r"→\s+(/\S+)")


class FindingCategory(str, Enum):
    UNDECLARED_CITATION = "undeclared_citation"
    UNUSED_DECLARATION = "unused_declaration"
    NONEXISTENT_CITATION = "nonexistent_citation"


@dataclass(frozen=True)
class AuditFinding:
    """One drift finding from auditing one artifact."""

    artifact: str
    category: FindingCategory
    path: str
    detail: str


@dataclass(frozen=True)
class ArtifactAuditResult:
    """All findings for one artifact, plus parsed data for the report."""

    artifact: str  # vault-relative path, e.g. "compiled/this-week.md"
    declared_sources: list[str]
    cited_paths: list[str]
    findings: list[AuditFinding]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Return `(frontmatter_yaml, body)` for a markdown file with `---` fences.

    Returns `("", text)` when the file has no frontmatter — that's a
    finding-worthy state in its own right but the caller decides how to
    treat it.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ("", text)
    closing = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing = i
            break
    if closing is None:
        return ("", text)
    fm = "\n".join(lines[1:closing])
    body = "\n".join(lines[closing + 1 :])
    return (fm, body)


def _parse_frontmatter_sources(fm_text: str) -> list[str]:
    """Return the `sources_read:` list from frontmatter, or [] on malformed."""
    if not fm_text:
        return []
    try:
        loaded = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        return []
    if not isinstance(loaded, dict):
        return []
    raw = loaded.get("sources_read", [])
    if not isinstance(raw, list):
        return []
    # Normalise: keep only string entries, strip whitespace.
    return [str(item).strip() for item in raw if isinstance(item, (str, bytes))]


def _extract_arrow_citations(body: str) -> list[str]:
    """Return every `→ /<path>` citation in the body, in order of appearance."""
    return _ARROW_RE.findall(body)


def _vault_relative_to_disk(vault_root: Path, vault_relative: str) -> Path:
    """Resolve a leading-slash vault-relative path to an absolute disk path."""
    return vault_root / vault_relative.lstrip("/")


def audit_artifact(vault_root: Path, artifact_path: Path) -> ArtifactAuditResult:
    """Audit one compiled artifact and return its findings.

    `artifact_path` is vault-relative (e.g. `Path("compiled/this-week.md")`).
    The artifact MUST exist on disk; the caller filters out missing ones
    before calling this function.
    """
    artifact_str = str(artifact_path).replace("\\", "/")
    full_path = vault_root / artifact_path
    text = _read_text(full_path)
    fm_text, body = _split_frontmatter(text)
    declared = _parse_frontmatter_sources(fm_text)
    cited = _extract_arrow_citations(body)

    declared_set = set(declared)
    cited_set = set(cited)

    findings: list[AuditFinding] = []

    for path in sorted(cited_set - declared_set):
        findings.append(
            AuditFinding(
                artifact=artifact_str,
                category=FindingCategory.UNDECLARED_CITATION,
                path=path,
                detail=(
                    "Body cites this path via an arrow, but the artifact's "
                    "`sources_read:` frontmatter list does not declare it."
                ),
            )
        )

    for path in sorted(declared_set - cited_set):
        findings.append(
            AuditFinding(
                artifact=artifact_str,
                category=FindingCategory.UNUSED_DECLARATION,
                path=path,
                detail=(
                    "Frontmatter declares this path in `sources_read:`, but "
                    "the body never cites it via an arrow."
                ),
            )
        )

    # Nonexistent citations — check both cited and declared paths against
    # the vault. We flag every path the artifact references (in either
    # surface) that doesn't resolve to a real file.
    all_referenced = sorted(cited_set | declared_set)
    for path in all_referenced:
        disk_path = _vault_relative_to_disk(vault_root, path)
        if not disk_path.exists():
            findings.append(
                AuditFinding(
                    artifact=artifact_str,
                    category=FindingCategory.NONEXISTENT_CITATION,
                    path=path,
                    detail=(
                        "Path is referenced by the artifact (in `sources_read:` "
                        "and/or via an arrow) but does not exist in the vault."
                    ),
                )
            )

    return ArtifactAuditResult(
        artifact=artifact_str,
        declared_sources=sorted(declared_set),
        cited_paths=sorted(cited_set),
        findings=findings,
    )


def audit_all(
    vault_root: Path, artifacts: tuple[Path, ...] = AUDITED_ARTIFACTS
) -> list[ArtifactAuditResult]:
    """Audit every artifact in `artifacts` that exists on disk.

    Artifacts that don't exist are silently skipped — a missing compile
    pass is the user's job to investigate, not the audit pass's. The
    skip is logged at INFO level so it's visible in scheduled runs.
    """
    results: list[ArtifactAuditResult] = []
    for artifact in artifacts:
        full = vault_root / artifact
        if not full.is_file():
            logger.info("skipping missing artifact: %s", artifact)
            continue
        results.append(audit_artifact(vault_root, artifact))
    return results


def _render_report(
    results: list[ArtifactAuditResult],
    *,
    refreshed: str | None = None,
) -> str:
    """Render the audit report as a markdown document.

    Frontmatter carries the run timestamp and category counts. Each
    audited artifact gets its own section listing findings or a "clean"
    marker.
    """
    if refreshed is None:
        refreshed = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    counts: dict[FindingCategory, int] = {c: 0 for c in FindingCategory}
    for r in results:
        for f in r.findings:
            counts[f.category] += 1
    total = sum(counts.values())

    parts: list[str] = [
        "---\n",
        "type: review\n",
        "artifact: audit-report\n",
        f"refreshed: {refreshed}\n",
        f"audited_count: {len(results)}\n",
        f"findings_total: {total}\n",
        f"findings_undeclared_citation: {counts[FindingCategory.UNDECLARED_CITATION]}\n",
        f"findings_unused_declaration: {counts[FindingCategory.UNUSED_DECLARATION]}\n",
        f"findings_nonexistent_citation: {counts[FindingCategory.NONEXISTENT_CITATION]}\n",
        "audit_pass_version: 1\n",
        "---\n",
        "\n",
        "# Audit report\n",
        "\n",
    ]
    if not results:
        parts.append(
            "_(no compiled artifacts found — nothing to audit)_\n"
            "\n"
            "---\n"
            "*Generated by `python -m plos.audit_pass`.*\n"
        )
        return "".join(parts)

    if total == 0:
        parts.append(
            f"**All {len(results)} audited artifacts passed.** "
            f"Every `→ /source/...` arrow is declared in `sources_read:`, "
            f"every declared path is cited at least once, and every path "
            f"resolves to an existing file in the vault.\n\n"
        )
    else:
        parts.append(
            f"**{total} finding(s) across {len(results)} audited artifact(s).** "
            f"undeclared: {counts[FindingCategory.UNDECLARED_CITATION]} · "
            f"unused: {counts[FindingCategory.UNUSED_DECLARATION]} · "
            f"nonexistent: {counts[FindingCategory.NONEXISTENT_CITATION]}.\n\n"
        )

    for r in results:
        parts.append(f"## /{r.artifact}\n\n")
        if not r.findings:
            parts.append(
                f"_(clean — {len(r.declared_sources)} declared, "
                f"{len(r.cited_paths)} cited, no drift)_\n\n"
            )
            continue
        for f in r.findings:
            label = f.category.value.replace("_", " ")
            parts.append(f"- **{label}** — `{f.path}`\n  {f.detail}\n")
        parts.append("\n")

    parts.append(
        "---\n"
        "*Generated by `python -m plos.audit_pass`.*\n"
    )
    return "".join(parts)


def _atomic_write(path: Path, content: str) -> None:
    """Write content to path via temp+rename. Mirrors compile_*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def run(vault_root: Path) -> tuple[Path, list[ArtifactAuditResult]]:
    """Audit all v1 compiled artifacts and write the report atomically.

    Returns `(report_path, results)`. Always exits with the report
    written — findings live in the report rather than affecting the
    process exit code. A future `--strict` flag (deferred) could
    promote findings into non-zero exits for CI use.
    """
    results = audit_all(vault_root)
    report = _render_report(results)
    target = vault_root / REPORT_PATH
    _atomic_write(target, report)
    total = sum(len(r.findings) for r in results)
    logger.info(
        "wrote %s (%d audited, %d finding(s))", target, len(results), total
    )
    return target, results


def _resolve_vault_root() -> Path:
    """Pull PLOS_VAULT_ROOT from env. Same shape as compile_this_week."""
    raw = os.environ.get("PLOS_VAULT_ROOT")
    if not raw:
        raise RuntimeError("PLOS_VAULT_ROOT not set in environment")
    p = Path(raw)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p.resolve()


def main() -> None:
    load_dotenv(override=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    vault_root = _resolve_vault_root()
    target, results = run(vault_root)
    total = sum(len(r.findings) for r in results)
    logger.info(
        "audit complete: %s (%d artifacts, %d findings)",
        target,
        len(results),
        total,
    )


if __name__ == "__main__":
    main()
