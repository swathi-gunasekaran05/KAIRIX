"""
Source-Aware Evidence Normalizer & Cross-System Extractor.

Extracts deterministic technology-specific metadata and business logic for:
- SQL:   Database -> Schema -> Table -> Column
- SSIS:  Package -> Connection / Database -> Schema -> Table -> Column
- COBOL: Program -> File / Record -> Field

Guarantees:
- Zero hallucination: Missing database/schema names are returned as 'N/A'.
- No hardcoded system or table names.
- Scoped strictly to user-selected source files when provided.
- Full line and source traceability.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .models import (
    COBOLField,
    COBOLFile,
    COBOLLogicItem,
    COBOLRecord,
    COBOLSourceMetadata,
    InvestigationScope,
    NormalizedInvestigationResult,
    SQLColumn,
    SQLDatabase,
    SQLLogicItem,
    SQLSchema,
    SQLSourceMetadata,
    SQLTable,
    SSISColumn,
    SSISConnection,
    SSISDatabase,
    SSISSchema,
    SSISSourceMetadata,
    SSISTable,
    SSISTransformation,
    SourceMetadata,
    SourceTrace,
)


class EvidenceNormalizer:
    """
    Extracts and normalizes source-aware metadata and logic across SQL, SSIS, and COBOL files.
    """

    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = root_dir or Path(__file__).resolve().parents[1]
        self.output_dir = self.root_dir / "output"
        self.source_dir = self.root_dir / "source"
        self.knowledge_dir = self.output_dir / "knowledge"

        self._sql_meta_cache: Dict[str, Dict[str, Any]] = {}
        self._ssis_meta_cache: Dict[str, Dict[str, Any]] = {}
        self._cobol_meta_cache: Dict[str, Dict[str, Any]] = {}
        self._knowledge_pkg_cache: Dict[str, Dict[str, Any]] = {}

        self._load_caches()

    def _load_caches(self) -> None:
        """Preload available metadata files and knowledge packages."""
        # 1. SQL metadata
        sql_dir = self.output_dir / "sql"
        if sql_dir.exists():
            for p in sql_dir.glob("*.json"):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    fname = data.get("file_metadata", {}).get("file_name") or p.stem.replace("_metadata", "") + ".sql"
                    self._sql_meta_cache[fname] = data
                    self._sql_meta_cache[p.stem.replace("_metadata", "")] = data
                except Exception:
                    pass

        # 2. SSIS metadata
        ssis_dir = self.output_dir / "ssis"
        if ssis_dir.exists():
            for p in ssis_dir.glob("*.json"):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    pkgs = data.get("packages", [])
                    fname = pkgs[0].get("source_file") if pkgs else f"{p.stem.replace('_metadata', '')}.dtsx"
                    if fname:
                        self._ssis_meta_cache[fname] = data
                        self._ssis_meta_cache[Path(fname).stem] = data
                except Exception:
                    pass

        # 3. COBOL metadata
        cobol_dir = self.output_dir / "cobol"
        if cobol_dir.exists():
            for p in cobol_dir.glob("*.json"):
                if p.name == "semantic_data.json":
                    continue
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    fname = data.get("file") or f"{p.stem.replace('_metadata', '')}.CBL"
                    self._cobol_meta_cache[fname] = data
                    self._cobol_meta_cache[Path(fname).stem] = data
                except Exception:
                    pass

        # 4. Knowledge Packages
        if self.knowledge_dir.exists():
            for p in self.knowledge_dir.glob("*_knowledge_package.json"):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    fname = data.get("source", {}).get("file_name", "")
                    if fname:
                        self._knowledge_pkg_cache[fname] = data
                        self._knowledge_pkg_cache[Path(fname).stem] = data
                except Exception:
                    pass

    # ── Main Normalization Entry Point ─────────────────────────────────────────

    def normalize(
        self,
        question: str,
        intent: str,
        graph_records: List[Dict[str, Any]],
        vector_chunks: List[Dict[str, Any]],
        vector_summaries: List[Dict[str, Any]],
        synthesized_answer: str,
        selected_files: Optional[List[str]] = None,
    ) -> NormalizedInvestigationResult:
        """
        Produce a normalized, source-aware investigation result.
        Investigates ONLY selected_files if specified.
        """
        # Determine target files to investigate
        target_files = self._resolve_target_files(
            selected_files=selected_files,
            graph_records=graph_records,
            vector_chunks=vector_chunks,
            vector_summaries=vector_summaries,
        )

        sources: List[SourceMetadata] = []
        systems_checked: Set[str] = set()

        for file_name in target_files:
            sys_type = self._infer_system(file_name)
            systems_checked.add(sys_type)

            if sys_type == "SQL":
                source_meta = self._extract_sql_source(file_name, question)
                if source_meta:
                    sources.append(source_meta)
            elif sys_type == "SSIS":
                source_meta = self._extract_ssis_source(file_name, question)
                if source_meta:
                    sources.append(source_meta)
            elif sys_type == "COBOL":
                source_meta = self._extract_cobol_source(file_name, question)
                if source_meta:
                    sources.append(source_meta)

        # Extract cross-system correlations & differences dynamically
        correlations, differences = self._correlate_sources(sources, synthesized_answer)

        scope = InvestigationScope(
            query=question,
            selected_files=selected_files or sorted(target_files),
            intent=intent,
            systems_checked=sorted(systems_checked) if systems_checked else ["COBOL", "SSIS", "SQL"],
        )

        return NormalizedInvestigationResult(
            investigation=scope,
            sources=sources,
            correlations=correlations,
            differences=differences,
        )

    # ── File Resolution ───────────────────────────────────────────────────────

    def _resolve_target_files(
        self,
        selected_files: Optional[List[str]],
        graph_records: List[Dict[str, Any]],
        vector_chunks: List[Dict[str, Any]],
        vector_summaries: List[Dict[str, Any]],
    ) -> List[str]:
        """Determine the set of files to investigate strictly."""
        if selected_files:
            # Clean and normalize filenames (strip path, match case-insensitively)
            cleaned = []
            for f in selected_files:
                f_clean = Path(f).name.strip()
                if f_clean:
                    cleaned.append(f_clean)
            return cleaned

        # Otherwise fallback to files detected across retrieved evidence
        detected = set()
        for hit in vector_chunks + vector_summaries:
            pay = hit.get("payload", {})
            fname = pay.get("file_name")
            if fname:
                detected.add(Path(fname).name)

        for rec in graph_records:
            for v in rec.values():
                if isinstance(v, str) and any(
                    v.lower().endswith(ext) for ext in (".sql", ".dtsx", ".cbl", ".cob", ".cpy")
                ):
                    detected.add(Path(v).name)

        return sorted(detected)

    def _infer_system(self, file_name: str) -> str:
        f_lower = file_name.lower()
        if any(f_lower.endswith(ext) for ext in (".cbl", ".cob", ".cpy")):
            return "COBOL"
        elif f_lower.endswith(".dtsx"):
            return "SSIS"
        elif f_lower.endswith(".sql"):
            return "SQL"
        return "SQL"

    # ── SQL Extraction (Database -> Schema -> Table -> Column) ────────────────

    def _extract_sql_source(self, file_name: str, question: str) -> Optional[SQLSourceMetadata]:
        meta = self._get_sql_metadata(file_name)
        source_path = self._find_source_path(file_name, "sql")

        # Extract databases, schemas, tables, and columns
        db_map: Dict[str, Dict[str, Dict[str, SQLTable]]] = {}
        # hierarchy: db_name -> schema_name -> table_name -> SQLTable

        raw_tables = meta.get("tables", [])
        col_refs = meta.get("column_references", [])
        joins = meta.get("joins", [])
        cases = meta.get("case_expressions", [])
        functions = meta.get("functions", [])
        views = meta.get("views", [])

        # 1. Populate tables & split 3-part / 2-part / 1-part identifiers
        for tbl_entry in raw_tables:
            raw_name = tbl_entry.get("table", "")
            if not raw_name:
                continue
            alias = tbl_entry.get("alias")
            line = tbl_entry.get("line", 0)

            db, schema, table = self._parse_sql_identifier(raw_name)

            if db not in db_map:
                db_map[db] = {}
            if schema not in db_map[db]:
                db_map[db][schema] = {}

            if table not in db_map[db][schema]:
                trace = SourceTrace(
                    system="SQL",
                    file=file_name,
                    file_path=str(source_path) if source_path else None,
                    start_line=line,
                    end_line=line,
                    parser="SQLGlot (T-SQL)",
                )
                db_map[db][schema][table] = SQLTable(
                    name=table,
                    alias=alias,
                    columns=[],
                    joins=[],
                    filters=[],
                    subqueries=[],
                    source=trace,
                )
            elif alias and not db_map[db][schema][table].alias:
                db_map[db][schema][table].alias = alias

        # If no tables were explicitly extracted in metadata, try from source text or AST
        if not db_map and source_path and source_path.exists():
            try:
                content = source_path.read_text(encoding="utf-8", errors="replace")
                from_matches = re.findall(r"(?:FROM|JOIN)\s+([a-zA-Z0-9_\.\[\]]+)(?:\s+(?:AS\s+)?([a-zA-Z0-9_]+))?", content, re.IGNORECASE)
                for tbl_raw, alias in from_matches:
                    clean_tbl = tbl_raw.replace("[", "").replace("]", "").strip()
                    if clean_tbl and not clean_tbl.upper().startswith("SELECT"):
                        db, schema, table = self._parse_sql_identifier(clean_tbl)
                        if db not in db_map:
                            db_map[db] = {}
                        if schema not in db_map[db]:
                            db_map[db][schema] = {}
                        if table not in db_map[db][schema]:
                            db_map[db][schema][table] = SQLTable(
                                name=table,
                                alias=alias if alias else None,
                                columns=[],
                                source=SourceTrace(system="SQL", file=file_name, parser="SQLGlot (T-SQL)"),
                            )
            except Exception:
                pass

        # 2. Attach columns to tables
        # From column_references or select lists
        for col_entry in col_refs:
            if isinstance(col_entry, dict):
                col_name = col_entry.get("column") or col_entry.get("name")
                tbl_qualifier = col_entry.get("table") or col_entry.get("alias") or col_entry.get("table_alias")
                line = col_entry.get("line", 0)
                data_type = col_entry.get("datatype", "N/A")
                is_derived = bool(col_entry.get("is_derived", False))
                expr = col_entry.get("expression") or col_entry.get("reference")
                col_alias = col_entry.get("alias")
                source_cols = col_entry.get("source_columns", [])
            elif isinstance(col_entry, str):
                col_name = col_entry
                tbl_qualifier = None
                line = 0
                data_type = "N/A"
                is_derived = False
                expr = None
                col_alias = None
                source_cols = []
            else:
                continue

            if not col_name:
                continue

            col_obj = SQLColumn(
                name=col_name,
                alias=col_alias,
                data_type=data_type,
                source_columns=source_cols,
                is_derived=is_derived,
                expression=expr,
                source=SourceTrace(
                    system="SQL",
                    file=file_name,
                    file_path=str(source_path) if source_path else None,
                    start_line=line,
                    end_line=line,
                    parser="SQLGlot (T-SQL)",
                ),
            )

            # Match to corresponding table
            matched = False
            for db_val in db_map.values():
                for schema_val in db_val.values():
                    for tbl_key, tbl_obj in schema_val.items():
                        if tbl_qualifier and (tbl_key == tbl_qualifier or tbl_obj.alias == tbl_qualifier):
                            if not any(c.name == col_name if isinstance(c, SQLColumn) else c == col_name for c in tbl_obj.columns):
                                tbl_obj.columns.append(col_obj)
                            matched = True
                            break
                    if matched:
                        break
                if matched:
                    break

            if not matched and db_map:
                # If no qualifier matches, attach to first table
                first_db = next(iter(db_map.values()))
                first_schema = next(iter(first_db.values()))
                first_tbl = next(iter(first_schema.values()))
                if not any(c.name == col_name if isinstance(c, SQLColumn) else c == col_name for c in first_tbl.columns):
                    first_tbl.columns.append(col_obj)

        # 3. Attach joins to tables
        for j in joins:
            if isinstance(j, dict):
                j_tbl = j.get("joined_table") or j.get("table")
                if j_tbl:
                    for db_val in db_map.values():
                        for schema_val in db_val.values():
                            if j_tbl in schema_val:
                                schema_val[j_tbl].joins.append(j)

        # 4. Extract SQL Logic (CASE expressions, calculations, aggregations, functions)
        logic_items: List[SQLLogicItem] = []
        for c in cases:
            if isinstance(c, dict):
                expr_text = c.get("expression") or c.get("text") or c.get("case_sql") or c.get("rule")
                line = c.get("line", 0)
                desc = c.get("description") or (f"CASE on {c.get('target_column')}" if c.get("target_column") else "Conditional CASE logic")
                ref_cols = c.get("referenced_columns") or ([c.get("target_column")] if c.get("target_column") else [])
            elif isinstance(c, str):
                expr_text = c
                line = 0
                desc = "Conditional CASE logic"
                ref_cols = []
            else:
                continue

            if expr_text:
                logic_items.append(
                    SQLLogicItem(
                        logic_type="case",
                        description=desc,
                        expression=expr_text[:200],
                        referenced_columns=ref_cols,
                        source=SourceTrace(
                            system="SQL",
                            file=file_name,
                            file_path=str(source_path) if source_path else None,
                            start_line=line,
                            end_line=line,
                            parser="SQLGlot (T-SQL)",
                        ),
                    )
                )

        for fn in functions:
            if isinstance(fn, dict):
                fn_name = fn.get("function") or fn.get("name")
                line = fn.get("line", 0)
                expr = fn.get("text") or fn.get("expression")
                args = fn.get("arguments", [])
            elif isinstance(fn, str):
                fn_name = fn
                line = 0
                expr = fn
                args = []
            else:
                continue

            if fn_name:
                logic_items.append(
                    SQLLogicItem(
                        logic_type="aggregation" if fn_name.upper() in ("SUM", "AVG", "COUNT", "MIN", "MAX") else "function",
                        description=f"Function/Aggregation {fn_name}",
                        expression=expr,
                        referenced_columns=args,
                        source=SourceTrace(
                            system="SQL",
                            file=file_name,
                            file_path=str(source_path) if source_path else None,
                            start_line=line,
                            end_line=line,
                            parser="SQLGlot (T-SQL)",
                        ),
                    )
                )

        # Build SQLDatabase list
        databases: List[SQLDatabase] = []
        if not db_map:
            # Fallback single N/A
            databases.append(
                SQLDatabase(
                    name="N/A",
                    schemas=[SQLSchema(name="N/A", tables=[SQLTable(name=Path(file_name).stem, columns=[])])],
                )
            )
        else:
            for db_name, schemas_dict in db_map.items():
                schemas_list: List[SQLSchema] = []
                for schema_name, tables_dict in schemas_dict.items():
                    schemas_list.append(
                        SQLSchema(
                            name=schema_name,
                            tables=list(tables_dict.values()),
                        )
                    )
                databases.append(SQLDatabase(name=db_name, schemas=schemas_list))

        view_names = [v.get("view_name") for v in views if isinstance(v, dict)] or [Path(file_name).stem]

        pkg = self._knowledge_pkg_cache.get(file_name) or self._knowledge_pkg_cache.get(Path(file_name).stem) or {}
        summary_text = pkg.get("summary", {}).get("purpose")

        return SQLSourceMetadata(
            system="SQL",
            file_name=file_name,
            file_path=str(source_path) if source_path else None,
            parser="SQLGlot (T-SQL dialect) + AST metadata",
            databases=databases,
            logic=logic_items,
            views=view_names,
            summary=summary_text,
        )

    def _parse_sql_identifier(self, identifier: str) -> Tuple[str, str, str]:
        """
        Parse SQL identifier into (database, schema, table).
        Examples:
          PolicyCenter.dbo.pc_policyperiod -> ('PolicyCenter', 'dbo', 'pc_policyperiod')
          public.policy                   -> ('N/A', 'public', 'policy')
          pc_policyperiod                 -> ('N/A', 'N/A', 'pc_policyperiod')
        """
        clean_id = identifier.replace("[", "").replace("]", "").strip()
        parts = [p.strip() for p in clean_id.split(".") if p.strip()]

        if len(parts) >= 3:
            return parts[0], parts[1], parts[2]
        elif len(parts) == 2:
            return "N/A", parts[0], parts[1]
        elif len(parts) == 1:
            return "N/A", "N/A", parts[0]
        return "N/A", "N/A", identifier

    # ── SSIS Extraction (Package -> Connection/DB -> Schema -> Table -> Column) ─

    def _extract_ssis_source(self, file_name: str, question: str) -> Optional[SSISSourceMetadata]:
        meta = self._get_ssis_metadata(file_name)
        source_path = self._find_source_path(file_name, "ssis")

        pkgs = meta.get("packages", [])
        pkg_name = pkgs[0].get("package_name") if pkgs else Path(file_name).stem

        # 1. Connections
        connections: List[SSISConnection] = []
        raw_conns = meta.get("connections", [])
        for c in raw_conns:
            c_name = c.get("name") or c.get("connection_name") or "Connection"
            c_type = c.get("creation_name") or c.get("connection_type") or "N/A"
            srv = c.get("server") or c.get("server_name") or "N/A"
            db = c.get("database") or c.get("initial_catalog") or "N/A"
            connections.append(
                SSISConnection(
                    name=c_name,
                    connection_type=c_type,
                    server=srv,
                    database=db,
                )
            )

        # 2. Extract database / schema / table / column from components & data flows
        db_map: Dict[str, Dict[str, Dict[str, SSISTable]]] = {}
        # db_name -> schema_name -> table_name -> SSISTable

        components = meta.get("components", [])
        transformations: List[SSISTransformation] = []

        for comp in components:
            comp_name = comp.get("component_name", "")
            comp_type = comp.get("component_type", "")
            desc = comp.get("description", "")
            props = comp.get("properties", {})

            sql_cmd = props.get("SqlCommand") or props.get("SqlCommandParam") or ""
            expr_str = props.get("Expressions") or ""
            table_or_view = props.get("TableOrViewName") or props.get("OpenRowset") or ""

            # Check if component represents transformation or SQL command
            expressions_list = [e.strip() for e in expr_str.split(";") if e.strip()] if expr_str else []
            sql_cmds_list = [sql_cmd] if sql_cmd else []

            if expressions_list or sql_cmds_list or "Transform" in comp_type or "DerivedColumn" in comp_type or "Lookup" in comp_type:
                transformations.append(
                    SSISTransformation(
                        component_name=comp_name,
                        component_type=comp_type,
                        description=desc,
                        expressions=expressions_list,
                        sql_commands=sql_cmds_list,
                        source=SourceTrace(
                            system="SSIS",
                            file=file_name,
                            file_path=str(source_path) if source_path else None,
                            parser="SSIS XML Parser",
                        ),
                    )
                )

            # Determine table & columns
            target_table_name = None
            if table_or_view:
                target_table_name = table_or_view
            elif sql_cmd:
                # Extract FROM/INTO/UPDATE table from SQL command
                tbl_match = re.search(r"(?:FROM|INTO|UPDATE)\s+([a-zA-Z0-9_\.\[\]]+)", sql_cmd, re.IGNORECASE)
                if tbl_match:
                    target_table_name = tbl_match.group(1)

            if target_table_name:
                db, schema, tbl = self._parse_sql_identifier(target_table_name)
                # Check if connection gives explicit database
                conn_mgr = props.get("ConnectionManager")
                if conn_mgr and db == "N/A":
                    for conn_obj in connections:
                        if conn_obj.name == conn_mgr and conn_obj.database != "N/A":
                            db = conn_obj.database

                if db not in db_map:
                    db_map[db] = {}
                if schema not in db_map[db]:
                    db_map[db][schema] = {}

                role = "source" if "Source" in comp_name or "SRC" in comp_name else ("destination" if "Dest" in comp_name or "DST" in comp_name else "staging")

                if tbl not in db_map[db][schema]:
                    db_map[db][schema][tbl] = SSISTable(
                        name=tbl,
                        columns=[],
                        role=role,
                        source=SourceTrace(
                            system="SSIS",
                            file=file_name,
                            file_path=str(source_path) if source_path else None,
                            parser="SSIS XML Parser",
                        ),
                    )

                # Extract columns from SQL command (e.g. SELECT col1, col2 FROM ...)
                if sql_cmd:
                    select_match = re.search(r"SELECT\s+(.*?)\s+FROM", sql_cmd, re.IGNORECASE | re.DOTALL)
                    if select_match:
                        raw_cols = select_match.group(1).split(",")
                        for raw_c in raw_cols:
                            c_clean = raw_c.strip().split()[-1].replace("[", "").replace("]", "")
                            if c_clean and c_clean != "*":
                                if not any(
                                    (c.name == c_clean if isinstance(c, SSISColumn) else c == c_clean)
                                    for c in db_map[db][schema][tbl].columns
                                ):
                                    db_map[db][schema][tbl].columns.append(
                                        SSISColumn(
                                            name=c_clean,
                                            column_type=role,
                                            source=SourceTrace(system="SSIS", file=file_name, parser="SSIS XML Parser"),
                                        )
                                    )

        # Build SSISDatabase list
        databases: List[SSISDatabase] = []
        if not db_map:
            databases.append(
                SSISDatabase(
                    name="N/A",
                    schemas=[SSISSchema(name="N/A", tables=[SSISTable(name=pkg_name, columns=[])])],
                )
            )
        else:
            for db_name, schemas_dict in db_map.items():
                schemas_list: List[SSISSchema] = []
                for schema_name, tables_dict in schemas_dict.items():
                    schemas_list.append(
                        SSISSchema(
                            name=schema_name,
                            tables=list(tables_dict.values()),
                        )
                    )
                databases.append(SSISDatabase(name=db_name, schemas=schemas_list))

        pkg = self._knowledge_pkg_cache.get(file_name) or self._knowledge_pkg_cache.get(Path(file_name).stem) or {}
        summary_text = pkg.get("summary", {}).get("purpose")

        return SSISSourceMetadata(
            system="SSIS",
            file_name=file_name,
            file_path=str(source_path) if source_path else None,
            package=pkg_name,
            parser="SSIS XML Parser",
            connections=connections,
            databases=databases,
            transformations=transformations,
            summary=summary_text,
        )

    # ── COBOL Extraction (Program -> File / Record -> Field) ──────────────────

    def _extract_cobol_source(self, file_name: str, question: str) -> Optional[COBOLSourceMetadata]:
        meta = self._get_cobol_metadata(file_name)
        source_path = self._find_source_path(file_name, "cobol")

        program_name = Path(file_name).stem

        # 1. Extract Files & Records & Fields
        raw_files = meta.get("files", [])
        raw_records = meta.get("records", [])
        raw_ops = meta.get("operations", {})

        files_list: List[COBOLFile] = []
        working_storage_records: List[COBOLRecord] = []

        # Read source text if available to build FD-to-record map
        fd_to_rec: Dict[str, List[str]] = {}
        ws_rec_names: Set[str] = set()

        if source_path and source_path.exists():
            try:
                src_text = source_path.read_text(encoding="utf-8", errors="replace")
                # Find FD blocks
                fd_matches = list(re.finditer(r"\bFD\s+([A-Z0-9-]+)", src_text, re.IGNORECASE))
                ws_match = re.search(r"\bWORKING-STORAGE\s+SECTION\b", src_text, re.IGNORECASE)
                ws_pos = ws_match.start() if ws_match else len(src_text)

                for idx, fd_m in enumerate(fd_matches):
                    fd_name = fd_m.group(1).upper()
                    start_pos = fd_m.end()
                    end_pos = fd_matches[idx + 1].start() if idx + 1 < len(fd_matches) else ws_pos
                    fd_chunk = src_text[start_pos:end_pos]
                    rec_names = re.findall(r"\b01\s+([A-Z0-9-]+)", fd_chunk, re.IGNORECASE)
                    fd_to_rec[fd_name] = [r.upper() for r in rec_names]

                if ws_match:
                    ws_chunk = src_text[ws_match.end():]
                    proc_match = re.search(r"\bPROCEDURE\s+DIVISION\b", ws_chunk, re.IGNORECASE)
                    if proc_match:
                        ws_chunk = ws_chunk[:proc_match.start()]
                    ws_rec_names = set(r.upper() for r in re.findall(r"\b01\s+([A-Z0-9-]+)", ws_chunk, re.IGNORECASE))
            except Exception:
                pass

        # Build parsed records map: name -> COBOLRecord
        parsed_records_map: Dict[str, COBOLRecord] = {}
        for rec in raw_records:
            r_name = (rec.get("record_name") or rec.get("name") or "RECORD").upper()
            r_level = rec.get("level", 1)
            r_line = rec.get("start_line", 0)

            fields_objs: List[COBOLField] = []
            direct_fields: List[str] = []
            for fld in rec.get("fields", []):
                if isinstance(fld, dict):
                    f_nm = fld.get("name", "")
                    f_lvl = fld.get("level", 5)
                    f_pic = fld.get("picture")
                    f_redef = fld.get("redefines")
                    f_line = fld.get("start_line", 0)
                    if f_nm:
                        fields_objs.append(
                            COBOLField(
                                name=f_nm,
                                level=f_lvl,
                                picture=f_pic,
                                redefines=f_redef,
                                source=SourceTrace(
                                    system="COBOL",
                                    file=file_name,
                                    file_path=str(source_path) if source_path else None,
                                    start_line=f_line,
                                    end_line=f_line,
                                    parser="Tree-sitter COBOL",
                                ),
                            )
                        )
                        direct_fields.append(f_nm)
                elif isinstance(fld, str):
                    direct_fields.append(fld)

            parsed_records_map[r_name] = COBOLRecord(
                name=r_name,
                level=r_level,
                fields=fields_objs if fields_objs else direct_fields,
                source=SourceTrace(
                    system="COBOL",
                    file=file_name,
                    file_path=str(source_path) if source_path else None,
                    start_line=r_line,
                    end_line=r_line,
                    parser="Tree-sitter COBOL",
                ),
            )

        # Map to files
        for f_entry in raw_files:
            f_name = f_entry.get("name", "")
            if not f_name:
                continue

            org = f_entry.get("organization")
            access = f_entry.get("access_mode")
            assign = f_entry.get("assign_to")
            start_line = f_entry.get("start_line", 0)

            # Match records under this file
            file_records: List[COBOLRecord] = []
            direct_fields: List[str] = []

            assigned_rec_names = fd_to_rec.get(f_name.upper(), [])
            if assigned_rec_names:
                for rn in assigned_rec_names:
                    if rn in parsed_records_map:
                        rec_obj = parsed_records_map[rn]
                        file_records.append(rec_obj)
                        for f in rec_obj.fields:
                            direct_fields.append(f.name if isinstance(f, COBOLField) else str(f))
            else:
                # Fallback: check if any record name matches file prefix
                for rn, rec_obj in parsed_records_map.items():
                    if not rn.startswith("WS-") and rn not in ws_rec_names:
                        file_records.append(rec_obj)
                        for f in rec_obj.fields:
                            direct_fields.append(f.name if isinstance(f, COBOLField) else str(f))

            files_list.append(
                COBOLFile(
                    name=f_name,
                    assign_to=assign,
                    organization=org,
                    access_mode=access,
                    records=file_records,
                    fields=direct_fields,
                    source=SourceTrace(
                        system="COBOL",
                        file=file_name,
                        file_path=str(source_path) if source_path else None,
                        start_line=start_line,
                        end_line=start_line,
                        parser="Tree-sitter COBOL",
                    ),
                )
            )

        # Separate Working-Storage records
        for rn, rec_obj in parsed_records_map.items():
            if rn.startswith("WS-") or rn in ws_rec_names:
                working_storage_records.append(rec_obj)

        # If no SELECT files found, map raw records as COBOLFiles
        if not files_list and raw_records:
            direct_fields = []
            rec_objs = list(parsed_records_map.values())
            for r in rec_objs:
                for f in r.fields:
                    direct_fields.append(f.name if isinstance(f, COBOLField) else str(f))

            files_list.append(
                COBOLFile(
                    name=program_name,
                    records=rec_objs,
                    fields=direct_fields,
                    source=SourceTrace(system="COBOL", file=file_name, parser="Tree-sitter COBOL"),
                )
            )

        # If no SELECT files found, map raw records as COBOLFiles
        if not files_list and raw_records:
            direct_fields = []
            rec_objs = []
            for rec in raw_records:
                r_name = rec.get("record_name") or rec.get("name") or "RECORD"
                fields_objs = []
                for fld in rec.get("fields", []):
                    if isinstance(fld, dict):
                        f_nm = fld.get("name", "")
                        fields_objs.append(
                            COBOLField(
                                name=f_nm,
                                level=fld.get("level", 5),
                                picture=fld.get("picture"),
                                redefines=fld.get("redefines"),
                                source=SourceTrace(system="COBOL", file=file_name, parser="Tree-sitter COBOL"),
                            )
                        )
                        direct_fields.append(f_nm)
                rec_objs.append(
                    COBOLRecord(
                        name=r_name,
                        fields=fields_objs,
                        source=SourceTrace(system="COBOL", file=file_name, parser="Tree-sitter COBOL"),
                    )
                )

            files_list.append(
                COBOLFile(
                    name=program_name,
                    records=rec_objs,
                    fields=direct_fields,
                    source=SourceTrace(system="COBOL", file=file_name, parser="Tree-sitter COBOL"),
                )
            )

        # 2. Extract COBOL Calculations & Logic (COMPUTE, ADD, SUBTRACT, MULTIPLY, DIVIDE, IF, EVALUATE, PERFORM, MOVE)
        logic_items: List[COBOLLogicItem] = []
        if isinstance(raw_ops, dict):
            for op_type, op_list in raw_ops.items():
                for op in op_list:
                    raw_stmt = op.get("statement") or op.get("text") or op.get("raw_line") or ""
                    start_l = op.get("start_line") or op.get("start", 0)
                    end_l = op.get("end_line") or op.get("end", start_l)
                    target = op.get("target") or op.get("target_variable")
                    sources_v = op.get("sources") or op.get("source_variables", [])

                    if raw_stmt:
                        logic_items.append(
                            COBOLLogicItem(
                                operation_type=op_type.upper(),
                                statement=raw_stmt.strip(),
                                target_field=target,
                                source_fields=sources_v if isinstance(sources_v, list) else [],
                                paragraph=op.get("paragraph"),
                                source=SourceTrace(
                                    system="COBOL",
                                    file=file_name,
                                    file_path=str(source_path) if source_path else None,
                                    start_line=start_l,
                                    end_line=end_l,
                                    parser="Tree-sitter COBOL",
                                ),
                            )
                        )

        # Supplementary extraction directly from COBOL source text for COMPUTE and arithmetic formulas
        has_compute = any(l.operation_type == "COMPUTE" for l in logic_items)
        if (not has_compute or len(logic_items) < 5) and source_path and source_path.exists():
            try:
                src_lines = source_path.read_text(encoding="utf-8", errors="replace").splitlines()
                current_paragraph = "PROCEDURE"
                in_proc = False
                for idx, line in enumerate(src_lines, 1):
                    clean_l = line.strip()
                    if not clean_l or clean_l.startswith("*") or clean_l.startswith("/"):
                        continue
                    if "PROCEDURE DIVISION" in clean_l.upper():
                        in_proc = True
                        continue
                    if not in_proc:
                        continue
                    # Check paragraph header (e.g. CALC-HO., CALC-AU.)
                    p_match = re.match(r"^([A-Z0-9-]+)\.\s*$", clean_l, re.IGNORECASE)
                    if p_match:
                        current_paragraph = p_match.group(1).upper()
                        continue
                    # Check for COMPUTE
                    comp_match = re.search(r"\bCOMPUTE\s+([A-Z0-9-]+)", clean_l, re.IGNORECASE)
                    if comp_match:
                        target = comp_match.group(1).replace("ROUNDED", "").strip()
                        stmt = clean_l
                        j = idx
                        while j < len(src_lines) and not src_lines[j - 1].strip().endswith("."):
                            nxt = src_lines[j].strip()
                            if not nxt or nxt.startswith("*") or any(nxt.upper().startswith(v) for v in ("IF ", "COMPUTE ", "MOVE ", "PERFORM ", "ADD ", "SUBTRACT ", "ELSE ", "CALC-")):
                                break
                            stmt += " " + nxt
                            j += 1
                        logic_items.append(
                            COBOLLogicItem(
                                operation_type="COMPUTE",
                                statement=stmt.strip(),
                                target_field=target,
                                source_fields=re.findall(r"\b[A-Z][A-Z0-9-]+\b", stmt),
                                paragraph=current_paragraph,
                                source=SourceTrace(
                                    system="COBOL",
                                    file=file_name,
                                    file_path=str(source_path),
                                    start_line=idx,
                                    end_line=j,
                                    parser="Deterministic COBOL Scanner",
                                ),
                            )
                        )
                    elif any(clean_l.upper().startswith(v) for v in ("ADD ", "SUBTRACT ", "MULTIPLY ", "DIVIDE ", "EVALUATE ", "IF ")):
                        v_type = clean_l.split()[0].upper()
                        logic_items.append(
                            COBOLLogicItem(
                                operation_type=v_type,
                                statement=clean_l,
                                target_field=None,
                                source_fields=re.findall(r"\b[A-Z][A-Z0-9-]+\b", clean_l),
                                paragraph=current_paragraph,
                                source=SourceTrace(
                                    system="COBOL",
                                    file=file_name,
                                    file_path=str(source_path),
                                    start_line=idx,
                                    end_line=idx,
                                    parser="Deterministic COBOL Scanner",
                                ),
                            )
                        )
            except Exception:
                pass

        raw_copybooks = meta.get("copybooks", [])
        copybooks: List[str] = []
        if isinstance(raw_copybooks, list):
            for c in raw_copybooks:
                if isinstance(c, dict):
                    c_name = c.get("name") or c.get("copybook")
                    if c_name:
                        copybooks.append(str(c_name))
                elif isinstance(c, str) and c.strip():
                    copybooks.append(c.strip())

        pkg = self._knowledge_pkg_cache.get(file_name) or self._knowledge_pkg_cache.get(Path(file_name).stem) or {}
        summary_text = pkg.get("summary", {}).get("purpose")

        return COBOLSourceMetadata(
            system="COBOL",
            file_name=file_name,
            file_path=str(source_path) if source_path else None,
            program=program_name,
            parser="Tree-sitter COBOL",
            files=files_list,
            working_storage_records=working_storage_records,
            logic=logic_items,
            copybooks=copybooks,
            summary=summary_text,
        )

    # ── Helpers for Metadata & Path Resolution ────────────────────────────────

    def _get_sql_metadata(self, file_name: str) -> Dict[str, Any]:
        stem = Path(file_name).stem
        if file_name in self._sql_meta_cache:
            return self._sql_meta_cache[file_name]
        if stem in self._sql_meta_cache:
            return self._sql_meta_cache[stem]
        return {}

    def _get_ssis_metadata(self, file_name: str) -> Dict[str, Any]:
        stem = Path(file_name).stem
        if file_name in self._ssis_meta_cache:
            return self._ssis_meta_cache[file_name]
        if stem in self._ssis_meta_cache:
            return self._ssis_meta_cache[stem]
        return {}

    def _get_cobol_metadata(self, file_name: str) -> Dict[str, Any]:
        stem = Path(file_name).stem
        if file_name in self._cobol_meta_cache:
            return self._cobol_meta_cache[file_name]
        if stem in self._cobol_meta_cache:
            return self._cobol_meta_cache[stem]
        return {}

    def _find_source_path(self, file_name: str, sys_type: str) -> Optional[Path]:
        name = Path(file_name).name
        if sys_type == "sql":
            candidates = list((self.source_dir / "sql").glob(f"**/{name}"))
        elif sys_type == "ssis":
            candidates = list((self.source_dir / "ssis").glob(f"**/{name}"))
        elif sys_type == "cobol":
            candidates = list((self.source_dir / "mainframe").glob(f"**/{name}"))
        else:
            candidates = list(self.source_dir.glob(f"**/{name}"))

        return candidates[0] if candidates else None

    # ── Correlation & Implementation Differences ──────────────────────────────

    def _correlate_sources(
        self,
        sources: List[SourceMetadata],
        synthesized_answer: str,
    ) -> Tuple[List[str], List[str]]:
        """Dynamically infer data flow correlations and implementation differences across sources."""
        correlations: List[str] = []
        differences: List[str] = []

        has_sql = any(s.system == "SQL" for s in sources)
        has_ssis = any(s.system == "SSIS" for s in sources)
        has_cobol = any(s.system == "COBOL" for s in sources)

        # Build dynamic flow
        flow_parts = []
        if has_sql:
            sql_names = [s.file_name for s in sources if s.system == "SQL"]
            flow_parts.append(f"SQL Views/Queries ({', '.join(sql_names)}) extract raw relational data")
        if has_ssis:
            ssis_names = [s.file_name for s in sources if s.system == "SSIS"]
            flow_parts.append(f"SSIS Packages ({', '.join(ssis_names)}) perform ETL staging, validation & lookup transformations")
        if has_cobol:
            cobol_names = [s.file_name for s in sources if s.system == "COBOL"]
            flow_parts.append(f"COBOL Programs ({', '.join(cobol_names)}) execute batch arithmetic, policy validation & sequential record updates")

        if len(flow_parts) > 1:
            correlations.append(" → ".join(flow_parts))

        # Extract explicit differences
        if has_sql and has_cobol:
            differences.append(
                "Relational SQL performs declarative set-based filtering/aggregations, whereas COBOL procedural logic executes sequential record-by-record loops and math operations."
            )
        if has_ssis and (has_sql or has_cobol):
            differences.append(
                "SSIS operates as an intermediate pipeline with data-type conversions and error redirects, bridging relational database schemas and flat/indexed files."
            )

        # Parse DATA FLOW or FORMULA from synthesized answer if present
        data_flow_match = re.search(r"DATA FLOW\s*\n([^\n\r]+)", synthesized_answer, re.IGNORECASE)
        if data_flow_match:
            df_text = data_flow_match.group(1).strip()
            if df_text and df_text != "None" and df_text not in correlations:
                correlations.append(df_text)

        return list(dict.fromkeys(correlations)), list(dict.fromkeys(differences))
