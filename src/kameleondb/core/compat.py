"""Compatibility shims for Python version differences."""

from __future__ import annotations

from datetime import timezone
from enum import Enum

UTC = timezone.utc  # noqa: UP017


class StrEnum(str, Enum):
    """String-valued enum base compatible with Python 3.10+."""

    def __str__(self) -> str:
        return str(self.value)
