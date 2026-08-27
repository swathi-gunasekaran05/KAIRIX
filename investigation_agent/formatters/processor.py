"""
Result Format Processor & Registry.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from .base import BaseFormatter
from .default_formatter import DefaultFormatter
from .table_column_formatter import DbTableColumnFormatter
from .cross_system_formatter import CrossSystemFormatter
from .lineage_formatter import FileLineageFormatter, SourceToTargetFormatter
from .business_logic_formatter import BusinessLogicFormatter
from .custom_formatter import CustomStructuredFormatter
from ..models import NormalizedInvestigationResult


class ResultFormatProcessor:
    """
    Central dispatcher and processor for all investigation result formats.
    """

    def __init__(self):
        self._formatters: Dict[str, BaseFormatter] = {}
        self._register_default_formatters()

    def _register_default_formatters(self):
        formatters = [
            DefaultFormatter(),
            FileLineageFormatter(),
            DbTableColumnFormatter(),
            SourceToTargetFormatter(),
            BusinessLogicFormatter(),
            CrossSystemFormatter(),
            CustomStructuredFormatter(),
        ]
        for f in formatters:
            self.register_formatter(f)

    def register_formatter(self, formatter: BaseFormatter):
        self._formatters[formatter.format_id.lower()] = formatter

    def list_formats(self) -> List[Dict[str, str]]:
        """List all available formats for UI/CLI selectors."""
        return [
            {"id": f.format_id, "name": f.display_name}
            for f in self._formatters.values()
        ]

    def format_result(
        self,
        normalized: NormalizedInvestigationResult,
        default_answer: str,
        format_type: str = "default",
        custom_fields: Optional[List[str]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Process and render the normalized result into the requested format.
        """
        fmt_key = format_type.lower().strip() if format_type else "default"
        
        # Alias normalization
        alias_map = {
            "default answer": "default",
            "db_table_column": "db_table_column",
            "database / table / column": "db_table_column",
            "table_column": "db_table_column",
            "tables": "db_table_column",
            "cross_system": "cross_system",
            "cross-system comparison": "cross_system",
            "cross_system_comparison": "cross_system",
            "comparison": "cross_system",
            "file lineage": "lineage",
            "lineage": "lineage",
            "source-to-target": "source_target",
            "source_to_target": "source_target",
            "source_target": "source_target",
            "business logic": "business_logic",
            "business_logic": "business_logic",
            "rules": "business_logic",
            "custom": "custom",
            "custom structured format": "custom",
        }
        canonical_key = alias_map.get(fmt_key, fmt_key)

        formatter = self._formatters.get(canonical_key)
        if not formatter:
            # Fallback to default formatter if unknown
            formatter = self._formatters.get("default", DefaultFormatter())

        merged_options = dict(options or {})
        if custom_fields:
            merged_options["custom_fields"] = custom_fields

        return formatter.format(
            normalized=normalized,
            default_answer=default_answer,
            options=merged_options,
        )
