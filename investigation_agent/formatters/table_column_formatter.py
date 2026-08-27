"""
Database / Table / Column structured result formatter.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from .base import BaseFormatter
from ..models import NormalizedInvestigationResult


class DbTableColumnFormatter(BaseFormatter):
    """Formats investigation results into Database / Table / Column view."""

    @property
    def format_id(self) -> str:
        return "db_table_column"

    @property
    def display_name(self) -> str:
        return "Database / Table / Column"

    def format(
        self,
        normalized: NormalizedInvestigationResult,
        default_answer: str = "",
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        headers = ["File Name", "System", "Database", "Table", "Column", "Logic", "Source Location"]
        rows: List[List[str]] = []

        for item in normalized.evidence:
            col_display = ", ".join(item.columns) if item.columns else "N/A"
            rows.append([
                item.file_name,
                item.system,
                item.database or "N/A",
                item.table or "N/A",
                col_display,
                item.logic or "N/A",
                item.source_location.to_display(),
            ])

        if not rows:
            return "No matching database, table, or column evidence found across the investigated systems."

        table = self.render_markdown_table(headers, rows)
        
        # Summary footer
        footer = f"\n\n**Total Matched Elements:** {len(rows)} across systems: {', '.join(normalized.investigation.systems_checked)}"
        return f"### DATABASE / TABLE / COLUMN INVESTIGATION\n\n{table}{footer}"
