import json
from graph import investigation_graph


# ============================================================
# DISPLAY FUNCTIONS
# ============================================================

def display_nlq(output):
    """Display natural-language investigation result."""

    print("\n" + "=" * 70)
    print("INVESTIGATION RESULT")
    print("=" * 70)

    print("\nANSWER")
    print("-" * 70)
    print(output.get("answer", "No answer available."))

    business_logic = output.get("business_logic", [])
    if business_logic:
        print("\nBUSINESS LOGIC")
        print("-" * 70)

        for item in business_logic:
            print(f"- {item}")

    findings = output.get("findings", [])
    if findings:
        print("\nFINDINGS")
        print("-" * 70)

        for finding in findings:
            if isinstance(finding, dict):
                print(f"- {finding.get('finding', '')}")

                if finding.get("source_file"):
                    print(
                        f"  Source: {finding['source_file']}"
                    )

                if finding.get("source_location"):
                    print(
                        f"  Location: "
                        f"{finding['source_location']}"
                    )

    relationships = output.get("relationships", [])
    if relationships:
        print("\nRELATIONSHIPS")
        print("-" * 70)

        for relationship in relationships:
            print(f"- {relationship}")

    gaps = output.get("gaps", [])
    if gaps:
        print("\nKNOWLEDGE GAPS")
        print("-" * 70)

        for gap in gaps:
            print(f"- {gap}")

    print("\nCONFIDENCE")
    print("-" * 70)
    print(output.get("confidence", "low").upper())


def display_table(output):
    """Display structured table output."""

    print("\n" + "=" * 70)
    print(output.get("title", "Investigation Table"))
    print("=" * 70)

    columns = output.get("columns", [])
    rows = output.get("rows", [])

    if not rows:
        print("\nNo rows found.")
        return

    # Calculate simple column widths.
    widths = []

    for index, column in enumerate(columns):

        values = [str(column)]

        for row in rows:
            if index < len(row):
                values.append(str(row[index]))

        # Prevent extremely wide terminal output.
        width = min(
            max(len(value) for value in values),
            30
        )

        widths.append(width)

    def format_value(value, width):
        value = str(value)

        if len(value) > width:
            value = value[: width - 3] + "..."

        return value.ljust(width)

    header = " | ".join(
        format_value(column, widths[i])
        for i, column in enumerate(columns)
    )

    print("\n" + header)

    print(
        "-+-".join(
            "-" * width
            for width in widths
        )
    )

    for row in rows:

        print(
            " | ".join(
                format_value(
                    row[i] if i < len(row) else "",
                    widths[i]
                )
                for i in range(len(columns))
            )
        )

    print(
        "\nConfidence:",
        output.get("confidence", "low").upper()
    )


def display_document(output):
    """Display predefined investigation document."""

    print("\n" + "=" * 70)
    print(output.get("title", "Investigation Report"))
    print("=" * 70)

    for section in output.get("sections", []):

        heading = section.get(
            "heading",
            "Section"
        )

        content = section.get(
            "content"
        )

        print(f"\n{heading.upper()}")
        print("-" * 70)

        if isinstance(content, list):

            for item in content:

                if isinstance(item, dict):
                    print(
                        json.dumps(
                            item,
                            indent=2,
                            ensure_ascii=False
                        )
                    )

                else:
                    print(f"- {item}")

        elif isinstance(content, dict):

            print(
                json.dumps(
                    content,
                    indent=2,
                    ensure_ascii=False
                )
            )

        else:
            print(content)

    print("\n" + "=" * 70)

    print(
        "FINAL CONFIDENCE:",
        output.get(
            "confidence",
            "low"
        ).upper()
    )

    print("=" * 70)


# ============================================================
# OUTPUT ROUTER
# ============================================================

def display_output(output):

    output_type = output.get(
        "type",
        "unknown"
    )

    if output_type == "nlq":
        display_nlq(output)

    elif output_type == "table":
        display_table(output)

    elif output_type == "document":
        display_document(output)

    else:
        print(
            json.dumps(
                output,
                indent=2,
                ensure_ascii=False
            )
        )


# ============================================================
# RUN INVESTIGATION
# ============================================================

def run_investigation(query):

    initial_state = {
        "user_query": query,
        "errors": []
    }

    try:

        result = investigation_graph.invoke(
            initial_state
        )

        output = result.get(
            "final_output"
        )

        if not output:
            print(
                "\nNo final output was generated."
            )

            return

        display_output(output)

    except Exception as exc:

        print(
            f"\nInvestigation Agent error: {exc}"
        )


# ============================================================
# INTERACTIVE MODE
# ============================================================

def main():

    print("\n" + "=" * 70)
    print("KAIRIX INVESTIGATION AGENT")
    print("=" * 70)

    print(
        "\nSupported request types:"
    )

    print(
        "  1. Natural-language investigation"
    )

    print(
        "  2. Structured table request"
    )

    print(
        "  3. Predefined document/report"
    )

    print(
        "\nType 'exit' to stop."
    )

    while True:

        query = input(
            "\nAsk Investigation Agent > "
        ).strip()

        if query.lower() in {
            "exit",
            "quit"
        }:
            print(
                "\nInvestigation Agent stopped."
            )
            break

        if not query:
            continue

        run_investigation(query)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()