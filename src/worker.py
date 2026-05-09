"""
Background worker — polls SQLite for new jobs, runs extraction pipeline,
merges into vault frontmatter.

Phase 1 target: skeleton with poll loop and post-consume hook integration.
Phase 2: first graduated extractor (utility bills) end-to-end.

See ARCHITECTURE.md → "The capture and extraction flow" for the full pipeline.
"""
