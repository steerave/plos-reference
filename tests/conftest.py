"""
Shared pytest fixtures and path setup.

The post-consume hook lives under `scripts/` (not a package) because it's
bind-mounted into the Paperless container. This conftest puts `scripts/` on
sys.path so tests can import the hook as a module.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
