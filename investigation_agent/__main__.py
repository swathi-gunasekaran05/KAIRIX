"""
Investigation Agent CLI — Layer 4 of KAIRIX Architecture.

The Investigation Agent answers user/analyst questions about legacy code,
business rules, data lineage, and system architecture by performing
combined retrieval across the Neo4j Knowledge Graph and Qdrant Vector DB,
with support for customizable result presentation formats.

Usage:
    # Ask in default conversational format:
    python -m investigation_agent "How is earned premium calculated?"

    # Ask in Cross-System Comparison format:
    python -m investigation_agent "Check if premium calculation code exists in SQL, SSIS, and COBOL" --format cross_system

    # Ask in Database / Table / Column format:
    python -m investigation_agent "What tables and columns are used for policy period?" --format db_table_column

    # Ask in Custom Structured format:
    python -m investigation_agent "Where is premium calculated?" --format custom --custom-fields "System,File Name,Table,Column,Logic,Location"

    # Interactive Q&A session:
    python -m investigation_agent --interactive
"""
from __future__ import annotations

import os
import warnings

# Suppress Hugging Face hub notices and progress logs
warnings.filterwarnings("ignore")
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from .agent import InvestigationAgent

# Ensure UTF-8 console output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


FORMAT_CHOICES = [
    "default",
    "lineage",
    "db_table_column",
    "source_target",
    "business_logic",
    "cross_system",
    "custom",
]

FORMAT_NAMES = {
    "default": "Default Answer (Conversational 7-Section Blueprint)",
    "lineage": "File Lineage",
    "db_table_column": "Database / Table / Column",
    "source_target": "Source-to-Target",
    "business_logic": "Business Logic & Rules",
    "cross_system": "Cross-System Comparison (SQL / SSIS / COBOL)",
    "custom": "Custom Structured Format",
}


def main():
    parser = argparse.ArgumentParser(
        prog="python -m investigation_agent",
        description="KAIRIX Layer 4: Investigation & Reverse Engineering Agent",
    )
    parser.add_argument(
        "question",
        nargs="?",
        type=str,
        help="The question to ask about the legacy systems",
    )
    parser.add_argument(
        "--format",
        "-f",
        type=str,
        default="default",
        choices=FORMAT_CHOICES,
        help="Output presentation format (default: default)",
    )
    parser.add_argument(
        "--custom-fields",
        type=str,
        default=None,
        help="Comma or pipe-separated custom field headers for custom format (e.g. 'System,File Name,Table,Column,Logic,Location')",
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
        help="Start an interactive multi-turn investigation session",
    )
    parser.add_argument(
        "--debug",
        "-d",
        action="store_true",
        help="Display internal debug diagnostics (intent, Cypher, retrieval counts, reasoning trace)",
    )

    args = parser.parse_args()

    if args.interactive:
        _run_interactive_session(args.top_k, debug=args.debug, initial_format=args.format, custom_fields=args.custom_fields)
    elif args.question:
        _ask_single_question(
            args.question,
            top_k=args.top_k,
            format_type=args.format,
            custom_fields=args.custom_fields,
            debug=args.debug,
        )
    else:
        parser.print_help()


def _ask_single_question(
    question: str,
    top_k: int,
    format_type: str = "default",
    custom_fields: Optional[str] = None,
    debug: bool = False,
) -> None:
    if debug:
        print("\n━━━ Investigation Agent (Layer 4) [DEBUG MODE] ━━━")
        print(f"Question: {question}")
        print(f"Format: {format_type}\n")

    fields_list = [f.strip() for f in custom_fields.split(",")] if custom_fields else None

    with InvestigationAgent(top_k_vectors=top_k, debug=debug) as agent:
        result = agent.ask(question, format_type=format_type, custom_fields=fields_list)

        output_text = result.formatted_output if format_type != "default" else result.answer
        print("\n" + output_text.strip() + "\n")

        if debug:
            print(f"{'═' * 60}")
            print("DEBUG DIAGNOSTICS")
            print(f"{'═' * 60}")
            print(f"Intent: {result.intent}")
            print(f"Format Used: {result.format_type}")
            print(f"Confidence Score: {result.confidence:.2f}")
            print(f"Graph Records Retrieved: {len(result.graph_evidence)}")
            print(f"Vector Context Chunks: {len(result.vector_evidence)}")
            if result.source_files:
                print(f"Detected Source Files: {', '.join(result.source_files)}")
            print(f"Reasoning Trace: {' → '.join(result.trace_path)}")
            print(f"{'═' * 60}\n")


def _run_interactive_session(
    top_k: int,
    debug: bool = False,
    initial_format: str = "default",
    custom_fields: Optional[str] = None,
) -> None:
    current_format = initial_format
    current_custom_fields = [f.strip() for f in custom_fields.split(",")] if custom_fields else [
        "File Name", "System", "Database", "Table", "Column", "Logic", "Source Location"
    ]

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║     KAIRIX Investigation & Reverse Engineering Console       ║")
    print("║     Layer 4 — Interactive Knowledge Retrieval Session        ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print("\n📋 Available Result Formats:")
    for idx, key in enumerate(FORMAT_CHOICES, 1):
        print(f"  [{idx}] {key.ljust(16)} — {FORMAT_NAMES.get(key, key)}")

    print("\n💡 Controls & Shortcuts:")
    print("  • Type your question and press Enter")
    print("  • ':f <name|1-7>' to change result format (e.g. ':f cross_system' or ':f 6')")
    print("  • ':custom <col1,col2...>' to set custom table headers")
    print("  • 'exit' or 'quit' to end session\n")

    if debug:
        print(">> DEBUG MODE: Enabled (displaying internal retrieval diagnostics)")

    with InvestigationAgent(top_k_vectors=top_k, debug=debug) as agent:
        while True:
            try:
                fmt_tag = f"Format: {current_format}"
                prompt_str = f"[{fmt_tag}] [Investigate] > "
                user_input = input(prompt_str).strip()
            except (KeyboardInterrupt, EOFError):
                print("\nExiting session.")
                break

            if not user_input:
                continue

            # Command handling
            if user_input.lower() in ("exit", "quit", "q"):
                print("Session ended.")
                break

            if user_input.startswith(":f ") or user_input.startswith(":format "):
                target_fmt = user_input.split(" ", 1)[1].strip()
                # Handle numeric selection
                if target_fmt.isdigit() and 1 <= int(target_fmt) <= len(FORMAT_CHOICES):
                    current_format = FORMAT_CHOICES[int(target_fmt) - 1]
                    print(f"✓ Result format switched to: {FORMAT_NAMES.get(current_format, current_format)}\n")
                    continue
                elif target_fmt.lower() in FORMAT_CHOICES:
                    current_format = target_fmt.lower()
                    print(f"✓ Result format switched to: {FORMAT_NAMES.get(current_format, current_format)}\n")
                    continue
                else:
                    print(f"⚠️ Unknown format '{target_fmt}'. Choose from: {', '.join(FORMAT_CHOICES)}\n")
                    continue

            if user_input.startswith(":custom "):
                raw_cols = user_input.split(" ", 1)[1].strip()
                if raw_cols:
                    if "|" in raw_cols:
                        current_custom_fields = [c.strip() for c in raw_cols.split("|") if c.strip()]
                    else:
                        current_custom_fields = [c.strip() for c in raw_cols.split(",") if c.strip()]
                    current_format = "custom"
                    print(f"✓ Custom fields set to: {current_custom_fields} (Format switched to 'custom')\n")
                    continue

            if user_input.startswith(":help"):
                print("\n📋 Formats: " + ", ".join(FORMAT_CHOICES))
                print("Commands: :f <name|1-7>, :custom <fields>, exit\n")
                continue

            # Execute investigation
            result = agent.ask(
                user_input,
                format_type=current_format,
                custom_fields=current_custom_fields if current_format == "custom" else None,
            )

            # Display output
            output_text = result.formatted_output if current_format != "default" else result.answer
            print("\n" + output_text.strip() + "\n")

            if debug:
                print(f"{'─' * 60}")
                print(f"[DEBUG] Intent: {result.intent} | Format: {result.format_type} | Confidence: {result.confidence:.2f}")
                print(f"[DEBUG] Graph Records: {len(result.graph_evidence)} | Vector Contexts: {len(result.vector_evidence)}")
                print(f"[DEBUG] Trace: {' → '.join(result.trace_path)}")
                print(f"{'─' * 60}\n")


if __name__ == "__main__":
    main()
