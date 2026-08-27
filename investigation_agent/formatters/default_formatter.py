"""
Default conversational answer formatter.
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from .base import BaseFormatter
from ..models import NormalizedInvestigationResult


class DefaultFormatter(BaseFormatter):
    """Preserves the existing conversational 7-section response blueprint."""

    @property
    def format_id(self) -> str:
        return "default"

    @property
    def display_name(self) -> str:
        return "Default Answer"

    def format(
        self,
        normalized: NormalizedInvestigationResult,
        default_answer: str = "",
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        return default_answer.strip()
