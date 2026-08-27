"""
Cross-system comparison result formatter.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from .base import BaseFormatter
from ..models import NormalizedInvestigationResult


class CrossSystemFormatter(BaseFormatter):
    """Formats investigation results into Cross-System Comparison view covering COBOL, SSIS, and SQL."""

    @property
    def format_id(self) -> str:
        return "cross_system"

    @property
    def display_name(self) -> str:
        return "Cross-System Comparison"

    def format(
        self,
        normalized: NormalizedInvestigationResult,
        default_answer: str = "",
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        output_parts: List[str] = []
        output_parts.append("### CROSS-SYSTEM INVESTIGATION\n")

        # 1. High-level Cross-System Status Table
        headers = ["System", "Status", "File", "Location", "Logic"]
        rows: List[List[str]] = []

        all_systems = ["SQL", "SSIS", "COBOL"]
        for sys_name in all_systems:
            sys_res = normalized.systems.get(sys_name)
            if sys_res and sys_res.status == "FOUND" and sys_res.evidence:
                for item in sys_res.evidence:
                    rows.append([
                        sys_name,
                        "FOUND",
                        item.file_name,
                        item.source_location.to_display(),
                        item.logic or item.transformation or "Relevant logic present",
                    ])
            else:
                rows.append([
                    sys_name,
                    "NOT FOUND",
                    "N/A",
                    "N/A",
                    "No matching logic detected in indexed code",
                ])

        table_str = self.render_markdown_table(headers, rows)
        output_parts.append(table_str)
        output_parts.append("\n")

        # 2. System-by-System Findings
        output_parts.append("#### SYSTEM BREAKDOWN\n")
        for sys_name in all_systems:
            sys_res = normalized.systems.get(sys_name)
            output_parts.append(f"**{sys_name}:**")
            if sys_res and sys_res.status == "FOUND" and sys_res.evidence:
                for item in sys_res.evidence:
                    loc = item.source_location.to_display()
                    tbl = f" (Table: `{item.table}`)" if item.table != "N/A" else ""
                    output_parts.append(f"- `{item.file_name}` [{loc}]{tbl}: {item.logic}")
            else:
                output_parts.append("- No matching logic or components found in repository.")
            output_parts.append("")

        # 3. Relationship & Correlation
        if normalized.correlations:
            output_parts.append("#### RELATIONSHIP / CORRELATION\n")
            for corr in normalized.correlations:
                output_parts.append(f"- {corr}")
            output_parts.append("")

        # 4. Differences across systems (if any)
        if normalized.differences:
            output_parts.append("#### IMPLEMENTATION DIFFERENCES\n")
            for diff in normalized.differences:
                output_parts.append(f"- {diff}")
            output_parts.append("")

        return "\n".join(output_parts).strip()
