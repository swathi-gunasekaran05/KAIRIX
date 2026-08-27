"""
Lineage and Source-to-Target result formatters.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from .base import BaseFormatter
from ..models import NormalizedInvestigationResult


class FileLineageFormatter(BaseFormatter):
    """Formats investigation results into File Lineage view."""

    @property
    def format_id(self) -> str:
        return "lineage"

    @property
    def display_name(self) -> str:
        return "File Lineage"

    def format(
        self,
        normalized: NormalizedInvestigationResult,
        default_answer: str = "",
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        headers = ["File Name", "System", "Upstream Source", "Downstream Target", "Flow Type", "Source Location"]
        rows: List[List[str]] = []

        for item in normalized.evidence:
            rows.append([
                item.file_name,
                item.system,
                item.upstream_source or "N/A",
                item.downstream_target or "N/A",
                item.data_flow_type or "FEEDS_INTO / PROCESSES",
                item.source_location.to_display(),
            ])

        if not rows:
            return "No lineage evidence found across the investigated systems."

        table = self.render_markdown_table(headers, rows)
        
        corrs = ""
        if normalized.correlations:
            corrs = "\n\n**Cross-System Data Lineage Flow:**\n" + "\n".join(f"- {c}" for c in normalized.correlations)

        return f"### FILE LINEAGE INVESTIGATION\n\n{table}{corrs}"


class SourceToTargetFormatter(BaseFormatter):
    """Formats investigation results into Source-to-Target data mapping view."""

    @property
    def format_id(self) -> str:
        return "source_target"

    @property
    def display_name(self) -> str:
        return "Source-to-Target"

    def format(
        self,
        normalized: NormalizedInvestigationResult,
        default_answer: str = "",
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        headers = ["Source System", "Source Entity / File", "Transformation Logic", "Target System", "Target Entity / File", "Location"]
        rows: List[List[str]] = []

        for item in normalized.evidence:
            rows.append([
                item.system,
                f"{item.file_name} ({item.table})" if item.table != "N/A" else item.file_name,
                item.transformation or item.logic or "Data extraction / load",
                item.downstream_target or "Downstream Consumer / Staging",
                item.table or "N/A",
                item.source_location.to_display(),
            ])

        if not rows:
            return "No source-to-target mappings found."

        table = self.render_markdown_table(headers, rows)
        return f"### SOURCE-TO-TARGET MAPPINGS\n\n{table}"
