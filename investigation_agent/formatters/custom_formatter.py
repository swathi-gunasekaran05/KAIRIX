"""
Custom user-defined structured format processor.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from .base import BaseFormatter
from ..models import NormalizedInvestigationResult, EvidenceItem


class CustomStructuredFormatter(BaseFormatter):
    """
    Dynamically renders investigation results according to user-selected fields.
    Validates field names and gracefully handles missing/unavailable attributes with 'N/A'.
    """

    @property
    def format_id(self) -> str:
        return "custom"

    @property
    def display_name(self) -> str:
        return "Custom Structured Format"

    # Supported field alias mapping to EvidenceItem properties
    FIELD_MAP: Dict[str, str] = {
        "file": "file_name",
        "file name": "file_name",
        "filename": "file_name",
        "source file": "file_name",
        "system": "system",
        "source system": "system",
        "database": "database",
        "db": "database",
        "schema": "schema_name",
        "table": "table",
        "table name": "table",
        "dataset": "table",
        "column": "columns",
        "columns": "columns",
        "field": "columns",
        "logic": "logic",
        "business logic": "logic",
        "business rule": "rule_id",
        "rule": "rule_id",
        "rule id": "rule_id",
        "condition": "condition",
        "transformation": "transformation",
        "formula": "transformation",
        "location": "location",
        "source location": "location",
        "line": "location",
        "lines": "location",
        "upstream": "upstream_source",
        "upstream source": "upstream_source",
        "downstream": "downstream_target",
        "downstream target": "downstream_target",
        "confidence": "confidence",
    }

    def format(
        self,
        normalized: NormalizedInvestigationResult,
        default_answer: str = "",
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        options = options or {}
        raw_fields = options.get("custom_fields", [])
        
        # Parse fields from list, comma-string, or pipe-separated string
        headers = self._parse_field_names(raw_fields)
        if not headers:
            headers = ["File Name", "System", "Database", "Table", "Column", "Logic", "Source Location"]

        rows: List[List[str]] = []
        for item in normalized.evidence:
            row: List[str] = []
            for header in headers:
                val = self._extract_field_value(item, header)
                row.append(val)
            rows.append(row)

        if not rows:
            return "No matching evidence found for the requested fields."

        table = self.render_markdown_table(headers, rows)
        return f"### CUSTOM STRUCTURED INVESTIGATION\n\n{table}"

    def _parse_field_names(self, raw_fields: Any) -> List[str]:
        if isinstance(raw_fields, str):
            if "|" in raw_fields:
                return [f.strip() for f in raw_fields.split("|") if f.strip()]
            elif "," in raw_fields:
                return [f.strip() for f in raw_fields.split(",") if f.strip()]
            elif raw_fields.strip():
                return [raw_fields.strip()]
        elif isinstance(raw_fields, (list, tuple)):
            res = []
            for f in raw_fields:
                if isinstance(f, str):
                    if "|" in f:
                        res.extend([x.strip() for x in f.split("|") if x.strip()])
                    elif "," in f:
                        res.extend([x.strip() for x in f.split(",") if x.strip()])
                    else:
                        res.append(f.strip())
            return [x for x in res if x]
        return []

    def _extract_field_value(self, item: EvidenceItem, field_name: str) -> str:
        norm_key = field_name.lower().strip()
        prop = self.FIELD_MAP.get(norm_key)

        if not prop:
            # Try direct property lookup
            if hasattr(item, norm_key):
                prop = norm_key
            else:
                return "N/A"

        if prop == "columns":
            return ", ".join(item.columns) if item.columns else "N/A"
        elif prop == "location":
            return item.source_location.to_display()
        elif prop == "confidence":
            return f"{item.confidence:.0%}"
        else:
            val = getattr(item, prop, None)
            if val is None or val == "" or str(val).lower() == "none":
                return "N/A"
            return str(val)
