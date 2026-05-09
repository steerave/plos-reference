"""
Paperless-ngx post-consume hook.
Inserts one row in the documents table with status='new' and exits in <100ms.

Phase 1 target.

See ARCHITECTURE.md → "The capture and extraction flow".
"""
