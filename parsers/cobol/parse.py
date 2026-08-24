import json
import re
from pathlib import Path

from tree_sitter_language_pack import get_parser


# ============================================================
# PROJECT CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

BASE_DIR = (
    PROJECT_ROOT
    / "source"
    / "mainframe"
    / "cobol"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "output"
    / "cobol"
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# TREE-SITTER
# ============================================================

parser = get_parser("cobol")


# ============================================================
# HELPERS
# ============================================================

def clean_spaces(text):
    return re.sub(r"\s+", " ", text).strip()


def unique(values):
    seen = set()
    result = []

    for value in values:
        if value is None:
            continue

        if isinstance(value, str):
            value = value.strip()

        if not value:
            continue

        key = (
            value
            if isinstance(value, str)
            else json.dumps(value, sort_keys=True)
        )

        if key not in seen:
            seen.add(key)
            result.append(value)

    return result


def walk_tree(root):
    """
    Iterative AST traversal.

    No recursive generator and no node.is_missing access.
    """
    stack = [root]

    while stack:
        node = stack.pop()
        yield node

        for child in reversed(node.children):
            stack.append(child)


def line_number(source, position):
    return source.count("\n", 0, position) + 1


# ============================================================
# SOURCE EXTRACTION
# ============================================================

def extract_program_id(source):
    match = re.search(
        r"\bPROGRAM-ID\.\s*([A-Z0-9_-]+)",
        source,
        re.IGNORECASE,
    )

    return (
        match.group(1).upper()
        if match
        else None
    )


def extract_divisions(source):
    matches = re.findall(
        r"^\s*([A-Z0-9-]+)\s+DIVISION\.",
        source,
        re.MULTILINE | re.IGNORECASE,
    )

    return unique(
        [x.upper() for x in matches]
    )


def extract_sections(source):
    matches = re.findall(
        r"^\s*([A-Z0-9-]+)\s+SECTION\.",
        source,
        re.MULTILINE | re.IGNORECASE,
    )

    return unique(
        [x.upper() for x in matches]
    )


def extract_paragraphs(source):
    paragraphs = []

    pattern = re.compile(
        r"(?m)^[ \t]{0,11}"
        r"([A-Z][A-Z0-9-]*|[0-9][0-9A-Z-]*)"
        r"\.\s*$"
    )

    ignored = {
        "IDENTIFICATION",
        "ENVIRONMENT",
        "DATA",
        "PROCEDURE",
        "FILE-CONTROL",
        "FILE",
        "WORKING-STORAGE",
        "LOCAL-STORAGE",
        "LINKAGE",
        "INPUT-OUTPUT",
    }

    for match in pattern.finditer(source):
        name = match.group(1).upper()

        if name in ignored:
            continue

        if name.endswith("DIVISION"):
            continue

        if name.endswith("SECTION"):
            continue

        paragraphs.append({
            "text": name + ".",
            "start_line": line_number(
                source,
                match.start(),
            ),
        })

    return unique(paragraphs)


def extract_copybooks(source):
    matches = re.findall(
        r"\bCOPY\s+([A-Z0-9_-]+)",
        source,
        re.IGNORECASE,
    )

    return [
        {"name": name.upper()}
        for name in unique(matches)
    ]


# ============================================================
# FILE DEFINITIONS
# ============================================================

def extract_files(source):
    files = {}

    for match in re.finditer(
        r"\bSELECT\s+([A-Z0-9-]+)"
        r"(?:\s+ASSIGN\s+TO\s+([A-Z0-9-]+))?"
        r"(.*?)(?=\.)",
        source,
        re.IGNORECASE | re.DOTALL,
    ):
        name = match.group(1).upper()

        assign_to = (
            match.group(2).upper()
            if match.group(2)
            else None
        )

        definition = match.group(3).upper()

        if "LINE SEQUENTIAL" in definition:
            organization = "LINE SEQUENTIAL"
        elif "INDEXED" in definition:
            organization = "INDEXED"
        elif "RELATIVE" in definition:
            organization = "RELATIVE"
        elif "SEQUENTIAL" in definition:
            organization = "SEQUENTIAL"
        else:
            organization = None

        files[name] = {
            "name": name,
            "assign_to": assign_to,
            "organization": organization,
            "status_variable": None,
        }

    for match in re.finditer(
        r"\bSELECT\s+([A-Z0-9-]+).*?"
        r"\bFILE\s+STATUS\s+IS\s+([A-Z0-9-]+)",
        source,
        re.IGNORECASE | re.DOTALL,
    ):
        name = match.group(1).upper()
        status = match.group(2).upper()

        if name in files:
            files[name]["status_variable"] = status

    for match in re.finditer(
        r"^\s*FD\s+([A-Z0-9-]+)\.",
        source,
        re.MULTILINE | re.IGNORECASE,
    ):
        name = match.group(1).upper()

        if name not in files:
            files[name] = {
                "name": name,
                "assign_to": None,
                "organization": None,
                "status_variable": None,
            }

    for match in re.finditer(
        r"^\s*SD\s+([A-Z0-9-]+)\.",
        source,
        re.MULTILINE | re.IGNORECASE,
    ):
        name = match.group(1).upper()

        files[name] = {
            "name": name,
            "assign_to": None,
            "organization": "SORT",
            "status_variable": None,
        }

    return list(files.values())


# ============================================================
# VARIABLES / RECORDS
# ============================================================

def extract_variables(source):
    variables = []

    pattern = re.compile(
        r"^\s*(\d{1,2})\s+"
        r"([A-Z0-9-]+)"
        r"(?:\s+PIC(?:TURE)?\s+([^\s.]+))?"
        r"(?:\s+VALUE\s+(.+?))?"
        r"\s*\.",
        re.MULTILINE | re.IGNORECASE,
    )

    for match in pattern.finditer(source):
        level = int(match.group(1))

        variables.append({
            "level": level,
            "name": match.group(2).upper(),
            "picture": (
                match.group(3).upper()
                if match.group(3)
                else None
            ),
            "value": (
                match.group(4).strip()
                if match.group(4)
                else None
            ),
            "start_line": line_number(
                source,
                match.start(),
            ),
        })

    return variables


def extract_records(variables):
    records = []
    current = None

    for variable in variables:

        if variable["level"] == 1:
            current = {
                "record_name": variable["name"],
                "level": 1,
                "fields": [],
                "start_line": variable.get(
                    "start_line"
                ),
            }

            records.append(current)
            continue

        if current is not None:
            if variable["level"] > 1:
                current["fields"].append({
                    "level": variable["level"],
                    "name": variable["name"],
                    "picture": variable.get("picture"),
                    "value": variable.get("value"),
                    "start_line": variable.get(
                        "start_line"
                    ),
                })

    return records


# ============================================================
# OPERATIONS
# ============================================================

def extract_operations(source):
    operations = {
        "perform": [],
        "read": [],
        "write": [],
        "move": [],
        "open": [],
        "close": [],
        "display": [],
        "if": [],
        "goto": [],
        "add": [],
    }

    patterns = {
        "perform": r"\bPERFORM\b.*?(?=\.)",
        "read": r"\bREAD\b.*?(?=\.)",
        "write": r"\bWRITE\b.*?(?=\.)",
        "move": r"\bMOVE\b.*?(?=\.)",
        "open": r"\bOPEN\b.*?(?=\.)",
        "close": r"\bCLOSE\b.*?(?=\.)",
        "display": r"\bDISPLAY\b.*?(?=\.)",
        "goto": r"\bGO\s+TO\b.*?(?=\.)",
        "add": r"\bADD\b.*?(?=\.)",
    }

    for key, pattern in patterns.items():
        matches = re.findall(
            pattern,
            source,
            re.IGNORECASE | re.DOTALL,
        )

        for match in matches:
            text = clean_spaces(match)

            if text and len(text) <= 500:
                operations[key].append(text)

        operations[key] = unique(
            operations[key]
        )

    # IF needs special handling.
    for match in re.finditer(
        r"\bIF\s+(.+?)(?=\b"
        r"(?:END-IF|MOVE|DISPLAY|PERFORM|READ|"
        r"WRITE|COMPUTE|ADD|SUBTRACT|MULTIPLY|DIVIDE)\b|\.)",
        source,
        re.IGNORECASE | re.DOTALL,
    ):
        condition = clean_spaces(
            match.group(1)
        )

        if condition:
            operations["if"].append(
                "IF " + condition
            )

    operations["if"] = unique(
        operations["if"]
    )

    return operations


def extract_performs(source):
    matches = re.findall(
        r"\bPERFORM\s+([A-Z0-9-]+)",
        source,
        re.IGNORECASE,
    )

    return unique(
        [x.upper() for x in matches]
    )


def extract_calls(source):
    matches = re.findall(
        r"\bCALL\s+['\"]?([A-Z0-9_-]+)",
        source,
        re.IGNORECASE,
    )

    return unique(
        [x.upper() for x in matches]
    )


def extract_sql(source):
    statements = []

    for match in re.finditer(
        r"EXEC\s+SQL(.*?)END-EXEC",
        source,
        re.IGNORECASE | re.DOTALL,
    ):
        statements.append(
            clean_spaces(match.group(1))
        )

    return unique(statements)


def extract_database_tables(sql_statements):
    tables = []

    for sql in sql_statements:
        matches = re.findall(
            r"\b(?:FROM|INTO|UPDATE|JOIN)"
            r"\s+([A-Z0-9_.-]+)",
            sql,
            re.IGNORECASE,
        )

        tables.extend(
            [x.upper() for x in matches]
        )

    return unique(tables)


def extract_file_operations(source):
    operations = []

    patterns = [
        ("READ", r"\bREAD\s+([A-Z0-9-]+)"),
        ("WRITE", r"\bWRITE\s+([A-Z0-9-]+)"),
        ("REWRITE", r"\bREWRITE\s+([A-Z0-9-]+)"),
        ("DELETE", r"\bDELETE\s+([A-Z0-9-]+)"),
        ("CLOSE", r"\bCLOSE\s+([A-Z0-9-]+)"),
    ]

    for operation, pattern in patterns:
        for match in re.finditer(
            pattern,
            source,
            re.IGNORECASE,
        ):
            operations.append({
                "operation": operation,
                "file": match.group(1).upper(),
            })

    for match in re.finditer(
        r"\bOPEN\s+"
        r"(?:INPUT|OUTPUT|I-O|EXTEND)?\s*"
        r"([A-Z0-9-]+)",
        source,
        re.IGNORECASE,
    ):
        operations.append({
            "operation": "OPEN",
            "file": match.group(1).upper(),
        })

    return unique(operations)


def extract_moves(source):
    moves = []

    pattern = re.compile(
        r"\bMOVE\s+(.+?)\s+TO\s+([A-Z0-9-]+)",
        re.IGNORECASE | re.DOTALL,
    )

    for match in pattern.finditer(source):
        source_value = clean_spaces(
            match.group(1)
        )

        if len(source_value) <= 200:
            moves.append({
                "source": source_value,
                "target": match.group(2).upper(),
            })

    return unique(moves)


def extract_conditions(source):
    conditions = []

    pattern = re.compile(
        r"\bIF\s+(.+?)(?=\b"
        r"(?:MOVE|DISPLAY|PERFORM|READ|WRITE|"
        r"COMPUTE|ADD|SUBTRACT|MULTIPLY|DIVIDE|"
        r"END-IF)\b|\.)",
        re.IGNORECASE | re.DOTALL,
    )

    for match in pattern.finditer(source):
        condition = clean_spaces(
            match.group(1)
        )

        if 0 < len(condition) <= 300:
            conditions.append(condition)

    return unique(conditions)


def extract_cics(source):
    statements = []

    for match in re.finditer(
        r"EXEC\s+CICS(.*?)END-EXEC",
        source,
        re.IGNORECASE | re.DOTALL,
    ):
        statements.append(
            clean_spaces(match.group(1))
        )

    return unique(statements)


# ============================================================
# SAFE TREE-SITTER METADATA
# ============================================================

def extract_tree_metadata(root):
    """
    Safe Tree-sitter metadata extraction.

    We only count node types here.
    We intentionally do NOT access:
        node.start_point
        node.end_point
        node.text
        node.is_missing
        node.children recursively

    This keeps the metadata stage safe for the
    COBOL grammar on Python 3.14.
    """

    node_count = 0
    error_count = 0
    type_counts = {}

    stack = [root]

    while stack:
        node = stack.pop()

        node_count += 1

        node_type = node.type

        type_counts[node_type] = (
            type_counts.get(node_type, 0) + 1
        )

        if node_type == "ERROR":
            error_count += 1

        for child in reversed(node.children):
            stack.append(child)

    return {
        "root_type": root.type,
        "has_error": root.has_error,
        "node_count": node_count,
        "error_count": error_count,
        "node_types": type_counts,
    }

# ============================================================
# RELATIONSHIPS
# ============================================================

def extract_relationships(file_name, metadata):
    relationships = []

    def add(source, relationship, target):
        if source and target:
            relationships.append({
                "source": source,
                "relationship": relationship,
                "target": target,
            })

    for copybook in metadata["copybooks"]:
        add(
            file_name,
            "USES_COPYBOOK",
            copybook["name"],
        )

    for record in metadata["records"]:
        add(
            file_name,
            "CONTAINS_RECORD",
            record["record_name"],
        )

        for field in record["fields"]:
            add(
                record["record_name"],
                "CONTAINS_FIELD",
                field["name"],
            )

    for paragraph in metadata["paragraphs"]:
        add(
            file_name,
            "CONTAINS_PARAGRAPH",
            paragraph["text"].rstrip("."),
        )

    for target in metadata["performs"]:
        add(
            file_name,
            "PERFORMS",
            target,
        )

    for target in metadata["calls"]:
        add(
            file_name,
            "CALLS",
            target,
        )

    for table in metadata["database_tables"]:
        add(
            file_name,
            "USES_TABLE",
            table,
        )

    relationship_map = {
        "READ": "READS",
        "WRITE": "WRITES",
        "REWRITE": "REWRITES",
        "DELETE": "DELETES",
        "OPEN": "OPENS",
        "CLOSE": "CLOSES",
    }

    for operation in metadata["file_operations"]:
        relationship = relationship_map.get(
            operation["operation"]
        )

        if relationship:
            add(
                file_name,
                relationship,
                operation["file"],
            )

    return unique(relationships)


# ============================================================
# PARSE ONE COBOL FILE
# ============================================================

def parse_cobol_file(file_path):

    print()
    print("=" * 80)
    print(f"PARSING: {file_path.name}")
    print("=" * 80)

    source = file_path.read_bytes()

    source_text = source.decode(
        "utf-8",
        errors="replace",
    )

    print("  [1/8] Tree-sitter parse...", flush=True)

    tree = parser.parse(source)
    root = tree.root_node

    print("  [2/8] Tree metadata...", flush=True)

    tree_metadata = extract_tree_metadata(root)

    print("  [3/8] Source extraction...", flush=True)

    program_id = extract_program_id(source_text)
    divisions = extract_divisions(source_text)
    sections = extract_sections(source_text)
    paragraphs = extract_paragraphs(source_text)

    print("  [4/8] Data extraction...", flush=True)

    files = extract_files(source_text)
    variables = extract_variables(source_text)
    records = extract_records(variables)
    copybooks = extract_copybooks(source_text)

    print("  [5/8] Operations...", flush=True)

    operations = extract_operations(source_text)
    performs = extract_performs(source_text)
    calls = extract_calls(source_text)

    print("  [6/8] I/O and database...", flush=True)

    sql_statements = extract_sql(source_text)
    database_tables = extract_database_tables(
        sql_statements
    )

    file_operations = extract_file_operations(
        source_text
    )

    moves = extract_moves(source_text)
    conditions = extract_conditions(source_text)
    cics_statements = extract_cics(source_text)

    print("  [7/8] Building metadata...", flush=True)

    metadata = {
        "file": file_path.name,
        "program_id": program_id,

        "parser": {
            "name": "Tree-sitter",
            "language": "COBOL",
            "grammar": "tree-sitter-language-pack",
        },

        "root": root.type,
        "has_errors": root.has_error,

        "divisions": divisions,
        "sections": sections,
        "paragraphs": paragraphs,

        "files": files,
        "variables": variables,
        "records": records,
        "copybooks": copybooks,

        "operations": operations,

        "performs": performs,
        "calls": calls,

        "sql_statements": sql_statements,
        "cics_statements": cics_statements,

        "database_tables": database_tables,
        "database_columns": [],

        "file_operations": file_operations,
        "moves": moves,
        "conditions": conditions,

        "tree_sitter": tree_metadata,

        "relationships": [],
        "parse_errors": [],
    }

    print("  [8/8] Relationships...", flush=True)

    metadata["relationships"] = extract_relationships(
        file_path.name,
        metadata,
    )

    if tree_metadata["error_count"] > 0:
        metadata["parse_errors"] = [
            {
                "type": "TREE_SITTER_ERROR",
                "count": tree_metadata["error_count"],
            }
        ]

    print("  PARSE COMPLETE", flush=True)

    return metadata


# ============================================================
# FILE DISCOVERY
# ============================================================

def discover_cobol_files():

    if not BASE_DIR.exists():
        return []

    return sorted(
        [
            path
            for path in BASE_DIR.iterdir()
            if path.is_file()
            and path.suffix.lower() in {
                ".cbl",
                ".cob",
            }
        ],
        key=lambda path: path.name.lower(),
    )


# ============================================================
# BATCH
# ============================================================

def main():

    print("=" * 80)
    print("COBOL BATCH PARSER")
    print("=" * 80)

    cobol_files = discover_cobol_files()

    print(
        f"COBOL files found: {len(cobol_files)}"
    )

    for file_path in cobol_files:
        print(
            f"  - {file_path.name}"
        )

    all_metadata = []

    successful = 0
    failed = 0

    for file_path in cobol_files:

        output_file = (
            OUTPUT_DIR
            / f"{file_path.stem}_metadata.json"
        )

        # Remove stale zero-byte output.
        if output_file.exists():
            output_file.unlink()

        try:

            metadata = parse_cobol_file(
                file_path
            )

            output_file.write_text(
                json.dumps(
                    metadata,
                    indent=4,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            all_metadata.append(
                metadata
            )

            successful += 1

            print(
                f"SUCCESS: {file_path.name}"
            )

            print(
                f"  Output: {output_file}"
            )

            print(
                f"  Size: "
                f"{output_file.stat().st_size}"
            )

            print(
                f"  Records: "
                f"{len(metadata['records'])}"
            )

            print(
                f"  Files: "
                f"{len(metadata['files'])}"
            )

            print(
                f"  Variables: "
                f"{len(metadata['variables'])}"
            )

            print(
                f"  Relationships: "
                f"{len(metadata['relationships'])}"
            )

        except Exception as exc:

            failed += 1

            print(
                f"FAILED: {file_path.name}"
            )

            print(
                f"  {type(exc).__name__}: {exc}"
            )

            if output_file.exists():
                output_file.unlink()

    semantic_data = {
        "source_directory": str(BASE_DIR),
        "total_programs": len(all_metadata),
        "programs": all_metadata,
    }

    semantic_output = (
        OUTPUT_DIR
        / "semantic_data.json"
    )

    semantic_output.write_text(
        json.dumps(
            semantic_data,
            indent=4,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 80)
    print("BATCH PARSING COMPLETED")
    print("=" * 80)

    print(
        f"Programs found : {len(cobol_files)}"
    )

    print(
        f"Programs parsed: {successful}"
    )

    print(
        f"Programs failed: {failed}"
    )

    print(
        f"Combined metadata: "
        f"{semantic_output}"
    )


if __name__ == "__main__":
    main()