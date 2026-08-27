"""
Base class for investigation result formatters.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from ..models import NormalizedInvestigationResult, InvestigationResult


class BaseFormatter(ABC):
    """Abstract base formatter converting normalized investigation results into structured displays."""

    @property
    @abstractmethod
    def format_id(self) -> str:
        """Unique identifier for this format (e.g. 'db_table_column', 'cross_system')."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable display name for UI dropdowns and CLI selectors."""
        pass

    @abstractmethod
    def format(
        self,
        normalized: NormalizedInvestigationResult,
        default_answer: str = "",
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Format the normalized investigation result into a final string representation.

        Args:
            normalized: Normalized multi-system evidence and system status.
            default_answer: The synthesized conversational answer (used as fallback/context).
            options: Optional format-specific options (e.g. custom_fields).

        Returns:
            Rendered formatted text or Markdown table.
        """
        pass

    @staticmethod
    def render_markdown_table(headers: List[str], rows: List[List[str]]) -> str:
        """Utility to render a clean GitHub Flavored Markdown table."""
        if not headers:
            return ""

        # Compute column widths
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    clean_cell = str(cell).replace("\n", " ").strip()
                    col_widths[i] = max(col_widths[i], len(clean_cell))

        # Build header line
        header_line = "| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"
        separator_line = "|-" + "-|-".join("-" * col_widths[i] for i in range(len(headers))) + "-|"

        # Build data rows
        row_lines = []
        for row in rows:
            padded_cells = []
            for i in range(len(headers)):
                cell_val = str(row[i]).replace("\n", " ").strip() if i < len(row) else "N/A"
                padded_cells.append(cell_val.ljust(col_widths[i]))
            row_lines.append("| " + " | ".join(padded_cells) + " |")

        return "\n".join([header_line, separator_line] + row_lines)
