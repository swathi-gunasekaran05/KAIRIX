"""
Business Logic result formatter.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from .base import BaseFormatter
from ..models import NormalizedInvestigationResult


class BusinessLogicFormatter(BaseFormatter):
    """Formats investigation results into Business Logic view."""

    @property
    def format_id(self) -> str:
        return "business_logic"

    @property
    def display_name(self) -> str:
        return "Business Logic"

    def format(
        self,
        normalized: NormalizedInvestigationResult,
        default_answer: str = "",
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        headers = ["Business Rule", "Condition", "Action / Formula", "Source File", "Source Location"]
        rows: List[List[str]] = []

        for item in normalized.evidence:
            rule_label = item.rule_id if item.rule_id else f"LOGIC-{item.system}"
            cond_display = item.condition if item.condition else "Standard execution flow"
            act_display = item.transformation or item.logic or "Data validation / assignment"
            
            rows.append([
                rule_label,
                cond_display,
                act_display,
                item.file_name,
                item.source_location.to_display(),
            ])

        if not rows:
            return "No business rules or transformation logic found."

        table = self.render_markdown_table(headers, rows)
        return f"### BUSINESS LOGIC & RULES INVESTIGATION\n\n{table}"
