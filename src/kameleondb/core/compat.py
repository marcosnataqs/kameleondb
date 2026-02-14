"""Compatibility shims for Python version differences."""

from __future__ import annotations

from datetime import timedelta, timezone
from enum import Enum

try:  # Python 3.11+
    from datetime import UTC  # type: ignore[attr-defined]
except ImportError:  # Python 3.10
    UTC = timezone(timedelta(0))

try:  # Python 3.11+
    from enum import StrEnum  # type: ignore[attr-defined]
except ImportError:  # Python 3.10

    class StrEnum(str, Enum):
        """String-valued enum base compatible with Python 3.10+."""

        def __str__(self) -> str:
            return str(self.value)
