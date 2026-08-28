"""
Investigation Agent CLI — Layer 4 of KAIRIX Architecture.

The Investigation Agent answers natural-language questions across all available
legacy source systems (COBOL, SSIS, SQL) using Knowledge Graph and Vector Database
retrieval combined with LLM reasoning.

Usage:
    # 1. Ask any question (automatically searches ALL available relevant sources):
    python -m investigation_agent "How is premium calculated?"

    # 2. Start an interactive investigation session:
    python -m investigation_agent --interactive

    # 3. Output raw structured JSON response for UI integration:
    python -m investigation_agent "How is premium calculated?" --json

    # 4. Separately inspect structured source metadata for a specific file:
    python -m investigation_agent --inspect PREMCALC.CBL
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()

# Configure Hugging Face authentication from environment
_hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")
if _hf_token:
    os.environ["HF_TOKEN"] = _hf_token
    os.environ["HUGGING_FACE_HUB_TOKEN"] = _hf_token
    os.environ.pop("HF_HUB_DISABLE_IMPLICIT_TOKEN", None)

warnings.filterwarnings("ignore")
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

from .agent import InvestigationAgent

# Ensure UTF-8 console output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def main():
    parser = argparse.ArgumentParser(
        prog="python -m investigation_agent",
        description="KAIRIX Layer 4: Multi-Source Investigation & Reverse Engineering Agent",
    )
    parser.add_argument(
        "question",
        nargs="?",
        type=str,
        default=None,
        help="The natural-language question to investigate across all available source systems",
    )
    parser.add_argument(
        "--inspect",
        "--metadata",
        "-m",
        type=str,
        nargs="?",
        const="all",
        default=None,
        help="Separately inspect structured source metadata (e.g. --inspect PREMCALC.CBL)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=8,
        help="Number of semantic vector results to retrieve (default: 8)",
    )
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Start an interactive investigation session",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw normalized JSON response model for UI integration",
    )
    parser.add_argument(
        "--debug",
        "-d",
        action="store_true",
        help="Display internal debug diagnostics (intent, Cypher, retrieval counts, reasoning trace)",
    )

    args = parser.parse_args()

    if args.interactive:
        _run_interactive_session(args.top_k, debug=args.debug)
    elif args.inspect is not None:
        target_file = None if args.inspect == "all" else args.inspect.strip()
        _inspect_metadata_only(
            target_file=target_file,
            top_k=args.top_k,
            json_output=args.json,
            debug=args.debug,
        )
    elif args.question:
        _ask_single_question(
            args.question,
            top_k=args.top_k,
            json_output=args.json,
            debug=args.debug,
        )
    else:
        parser.print_help()


def _print_sources_breakdown(sources: list) -> None:
    """Print human-readable source-aware breakdown for separate metadata view."""
    if not sources:
        return
    print(f"\n{'═' * 60}")
    print("STRUCTURED SOURCE METADATA VIEW")
    print(f"{'═' * 60}")
    for src in sources:
        if src.system == "SQL":
            print(f"\n[SQL] File: {src.file_name}")
            for db in src.databases:
                print(f"  Database: {db.name}")
                for sc in db.schemas:
                    print(f"    Schema: {sc.name}")
                    for tbl in sc.tables:
                        col_names = [c.name if hasattr(c, "name") else str(c) for c in tbl.columns]
                        print(f"      Table: {tbl.name} (Columns: {len(col_names)})")
                        if col_names:
                            print(f"        -> {', '.join(col_names[:8])}")
            if src.logic:
                print(f"  Business Logic / CASE rules: {len(src.logic)} items extracted")
        elif src.system == "SSIS":
            print(f"\n[SSIS] Package: {src.package} (File: {src.file_name})")
            for db in src.databases:
                print(f"  Database: {db.name}")
                for sc in db.schemas:
                    print(f"    Schema: {sc.name}")
                    for tbl in sc.tables:
                        col_names = [c.name if hasattr(c, "name") else str(c) for c in tbl.columns]
                        print(f"      Table: {tbl.name} (Role: {tbl.role})")
                        if col_names:
                            print(f"        -> {', '.join(col_names[:8])}")
            if src.transformations:
                print(f"  Transformations / SQL Tasks: {len(src.transformations)} items extracted")
        elif src.system == "COBOL":
            print(f"\n[COBOL] Program: {src.program} (File: {src.file_name})")
            for fl in src.files:
                print(f"  File / Record: {fl.name}")
                if fl.fields:
                    print(f"    Fields ({len(fl.fields)}): {', '.join(fl.fields[:8])}")
                for rec in fl.records:
                    rec_fields = [f.name if hasattr(f, "name") else str(f) for f in rec.fields]
                    if rec_fields:
                        print(f"    Record: {rec.name} -> {', '.join(rec_fields[:6])}")
            if src.logic:
                print(f"  Calculations & Statements: {len(src.logic)} extracted")
    print(f"{'═' * 60}\n")


def _inspect_metadata_only(
    target_file: Optional[str] = None,
    top_k: int = 8,
    json_output: bool = False,
    debug: bool = False,
) -> None:
    """Inspect and display metadata structure separately from normal Q&A."""
    selected_files = [target_file] if target_file and target_file != "all" else None
    with InvestigationAgent(top_k_vectors=top_k, debug=debug) as agent:
        normalized = agent.get_metadata(selected_files=selected_files)

        if json_output:
            print(normalized.model_dump_json(indent=2))
            return

        target_label = target_file if target_file else "all indexed files"
        print(f"\n✓ Extracted structured source metadata for: {target_label}")
        _print_sources_breakdown(normalized.sources)


def _ask_single_question(
    question: str,
    top_k: int = 8,
    json_output: bool = False,
    debug: bool = False,
) -> None:
    if debug:
        print("\n━━━ Investigation Agent (Layer 4) [DEBUG MODE] ━━━")
        print(f"Question: {question}")
        print("Scope: Automatic multi-source discovery (COBOL, SSIS, SQL)\n")

    with InvestigationAgent(top_k_vectors=top_k, debug=debug) as agent:
        result = agent.ask(question)

        if json_output:
            print(result.model_dump_json(indent=2))
            return

        # Normal investigation answer ONLY:
        # Ends after GAPS (or last section). No metadata dump appended!
        print("\n" + result.answer.strip() + "\n")

        if debug:
            print(f"{'═' * 60}")
            print("DEBUG DIAGNOSTICS")
            print(f"{'═' * 60}")
            print(f"Intent: {result.intent}")
            print(f"Confidence Score: {result.confidence:.2f}")
            print(f"Graph Records Retrieved: {len(result.graph_evidence)}")
            print(f"Vector Context Chunks: {len(result.vector_evidence)}")
            if result.source_files:
                print(f"Source Files Investigated: {', '.join(result.source_files)}")
            print(f"Reasoning Trace: {' → '.join(result.trace_path)}")
            print(f"{'═' * 60}\n")


def _run_interactive_session(
    top_k: int,
    debug: bool = False,
) -> None:
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║     KAIRIX Investigation & Reverse Engineering Console       ║")
    print("║     Layer 4 — Automatic Multi-Source Knowledge Retrieval     ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    print("\n💡 Controls & Commands:")
    print("  • Type your question and press Enter (automatically searches COBOL, SSIS, SQL)")
    print("  • ':inspect <file>' to view separate structured metadata for a file")
    print("  • 'exit' or 'quit' to end session\n")

    if debug:
        print(">> DEBUG MODE: Enabled\n")

    with InvestigationAgent(top_k_vectors=top_k, debug=debug) as agent:
        while True:
            try:
                user_input = input("[Investigate] > ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nExiting session.")
                break

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit", "q"):
                print("Session ended.")
                break

            if user_input.startswith(":inspect") or user_input.startswith(":metadata") or user_input.startswith(":show"):
                parts = user_input.split(maxsplit=1)
                file_target = parts[1].strip() if len(parts) > 1 else None
                selected = [file_target] if file_target else None
                meta = agent.get_metadata(selected_files=selected)
                _print_sources_breakdown(meta.sources)
                continue

            if user_input.startswith(":help"):
                print("\nType your question directly to investigate, ':inspect [file]' for metadata, or 'exit' to quit.\n")
                continue

            # Execute normal investigation question
            result = agent.ask(user_input)
            # Print ONLY the clean conversational answer
            print("\n" + result.answer.strip() + "\n")

            if debug:
                print(f"{'─' * 60}")
                print(f"[DEBUG] Intent: {result.intent} | Confidence: {result.confidence:.2f}")
                print(f"[DEBUG] Sources: {', '.join([s.file_name for s in result.sources])}")
                print(f"[DEBUG] Trace: {' → '.join(result.trace_path)}")
                print(f"{'─' * 60}\n")


if __name__ == "__main__":
    main()
