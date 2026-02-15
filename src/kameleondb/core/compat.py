"""Compatibility shims for Python version differences.

Python 3.11+ is required, so these are simple re-exports.
"""

from __future__ import annotations

from datetime import UTC
from enum import StrEnum

__all__ = ["UTC", "StrEnum"]
