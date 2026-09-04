"""
Investigation Agent prompt templates.
"""

# ── Intent Classification ──────────────────────────────────────────────────────
INTENT_CLASSIFICATION_PROMPT = """You are a system analyst working with a legacy insurance system knowledge base.

Classify the following user question into EXACTLY ONE of these intents:
- calculation      — asks how a metric/value is calculated, formulas, math logic (e.g. "How is premium calculated?", "What is the formula for earned premium?")
- lineage          — asks where an entity comes from, data flow, what reads/writes a file/table (e.g. "Where does PREMIUM-OUT come from?", "What does PREMCALC read?")
- impact_analysis  — asks what is affected if a file or component changes (e.g. "What will be affected if EARNPREM.CBL is changed?")
- relationship     — asks how multiple files/programs/tables relate to each other (e.g. "How does EARNPREM.CBL relate to PolicyCenter tables?")
- source_lookup    — asks which file/program is responsible for an action or rule (e.g. "Which COBOL program calculates written premium?")
- definition       — asks what a specific entity, variable, table or term is or means
- comparison       — asks how two programs, tables, or rules compare or differ
- validation       — asks about validation checks, error conditions, or business rule compliance
- semantic         — general conceptual or narrative question about system behavior

Question: {question}

Respond with ONLY the single intent name (e.g. calculation, lineage, impact_analysis, relationship, source_lookup, definition, comparison, validation, semantic).
"""

# ── Cypher Generation ──────────────────────────────────────────────────────────
CYPHER_GENERATION_PROMPT = """You are a Neo4j Cypher expert working with a legacy insurance system knowledge graph.

GRAPH SCHEMA:

Node types:
- :Artifact {{id, file_name, source_type, purpose, business_domain, total_lines}}
- :Entity {{id, name, entity_type, entity_label, source_file, data_type, description}}
- :BusinessRule {{id, description, source_file}}
- :Transformation {{id, rule_id, rule_type, description, expression, source_file}}

Key relationships:
- (:Artifact)-[:CONTAINS]->(:Entity) — an artifact file contains entities
- (:Artifact)-[:HAS_RULE]->(:BusinessRule) — an artifact has business rules
- (:Artifact)-[:HAS_TRANSFORMATION]->(:Transformation) — transformations
- (:Entity)-[:READS_FROM]->(:Entity) — data read lineage (edge has source_file property)
- (:Entity)-[:WRITES_TO]->(:Entity) — data write lineage (edge has source_file property)
- (:Entity)-[:CONTAINS]->(:Entity) — hierarchical (e.g. table contains columns)
- (:Entity)-[:USES]->(:Entity) — entity uses another (edge has source_file property)

IMPORTANT: Lineage edges (READS_FROM, WRITES_TO, USES, etc.) are between Entity nodes,
NOT from Artifact nodes. They have a `source_file` property on the EDGE that indicates
which file established the relationship.

QUERY PATTERNS:

To find what a specific file reads from or writes to:
  MATCH (src)-[r:READS_FROM {{source_file: 'FILENAME'}}]->(t:Entity)
  RETURN DISTINCT src.name AS program, t.name AS target, t.entity_type AS target_type

To find where an entity comes from or which programs write to it:
  MATCH (src:Entity)-[r:WRITES_TO|FEEDS_INTO|DERIVES_FROM]->(t:Entity)
  WHERE toLower(t.name) = toLower('ENTITY_NAME') OR t.id CONTAINS 'ENTITY_NAME'
  RETURN DISTINCT src.name AS writer, src.entity_type AS writer_type, r.source_file AS source_file, type(r) AS rel_type, t.name AS target

To find impact or dependencies for a file / program:
  MATCH (src)-[r {{source_file: 'FILENAME'}}]->(tgt:Entity)
  RETURN DISTINCT src.name AS from_entity, type(r) AS relationship, tgt.name AS to_entity, tgt.source_file AS target_file
  UNION
  MATCH (src:Entity)-[r]->(tgt {{source_file: 'FILENAME'}})
  RETURN DISTINCT src.name AS from_entity, src.source_file AS source_file, type(r) AS relationship, tgt.name AS to_entity

To find cross-file data flow:
  MATCH (src)-[r]->(t:Entity)<-[r2]-(other)
  WHERE r.source_file <> r2.source_file
  RETURN DISTINCT src.name, r.source_file, type(r), t.name, type(r2), r2.source_file, other.name

User question: {question}

Write a Cypher query to retrieve the most relevant graph data to answer this question.
- Use LIMIT to cap results (max 20).
- Return human-readable fields (names, descriptions, types).
- Use case-insensitive matching (e.g. toLower(t.name) = toLower('...')) for entity names.

Return ONLY the Cypher query, no explanation, no markdown.
"""

# ── Answer Synthesis ───────────────────────────────────────────────────────────
ANSWER_SYNTHESIS_PROMPT = """You are a senior insurance legacy systems reverse-engineering specialist.
You have been asked a question and retrieved evidence from a Neo4j knowledge graph and Pinecone vector database across COBOL, SSIS, and SQL sources.

Question:
{question}

Graph Evidence (Neo4j results):
{graph_evidence}

Semantic Evidence (relevant source code / summaries):
{vector_evidence}

Synthesize a precise, question-driven, non-redundant reverse-engineering response based ONLY on verified source evidence.

CRITICAL RULES:
1. SINGLE UNIFIED STRUCTURE (NO SEPARATE SYSTEM SECTIONS WITH DUPLICATE SOURCES):
   - Synthesize the response into a SINGLE cohesive structure.
   - DO NOT create separate top-level headings for each system (e.g. DO NOT create `## COBOL`, `## SSIS`, `## SQL` each with their own separate `### Sources` or `### Formula` blocks).
   - If the question involves multiple systems or a cross-system flow:
     • Trace the end-to-end journey in one unified sequence under `### End-to-End Flow` (e.g. 1. Origin in COBOL -> 2. Movement & Validation in SSIS -> 3. Consumption & Reporting in SQL).
     • Consolidate all verified files into a SINGLE `### Sources` list at the bottom.
   - If the question involves only one system (e.g. calculation in COBOL or pipeline in SSIS):
     • Focus strictly on that system without mentioning or creating dummy sections for unrelated systems.

2. FORMULAS MUST BE HUMAN-READABLE MATHEMATICAL EQUATIONS (NO RAW CODE DUMPS):
   - Express all calculations as clean mathematical equations using standard business names:
     • Example: `Written Premium = Base ($100.00) + (0.2% × Property Value) + (0.1% × Coverage Limit) − Deductible Discount`
     • DO NOT dump raw code statements or internal variables like `WS-DISCOUNT = WS-DEDUCT-TOTAL * WS-HO-DED-RATE` or SQL `CASE WHEN ...` blocks.
   - Include constants, percentages, minimum floors, and caps directly in the equation.
   - Translate internal code variables into their plain business meaning (e.g. `Property Value` instead of `WS-RISK-VALUE`, `Elapsed Days` instead of `WS-EARNED-DAYS`).

3. CONCISE & TARGETED FORMAT (SINGLE SECTION LAYOUT):
   - Provide only the relevant subsections needed to answer the question:
     - **ANSWER**: Direct, 1-2 paragraph executive summary explaining the answer or end-to-end flow.
     - **### End-to-End Flow** (for cross-system questions or data pipelines): Unified sequential flow (Step 1 -> Step 2 -> Step 3).
     - **### Key Logic & Formulas** (for calculations or business rules): Clean mathematical equations and business rules in a single list.
     - **### Sources**: A SINGLE consolidated list of all verified source files across systems.
     - **CONFIDENCE**: A single overall confidence assessment.
   - NEVER duplicate `### Sources` or confidence across multiple headers.

4. ZERO HALLUCINATION:
   - Base every statement strictly on the provided evidence. Never invent rules or parameters.

5. NO SOURCES FOR IRRELEVANT OR UNVERIFIED QUESTIONS:
   - If the question is off-topic, not relevant, or no verified evidence exists in the retrieved context:
     • State clearly in the ANSWER section that no relevant evidence exists in the indexed legacy codebase.
     • DO NOT output any system subsections, flow, formulas, or Sources.
     • Omit the Sources section completely. Never list unrelated or dummy source files.

REQUIRED OUTPUT STRUCTURE:

ANSWER
[Direct, cohesive answer explaining the core concept or end-to-end flow directly across all relevant systems]

### End-to-End Flow (Include for cross-system queries or data pipelines; omit if answering a single calculation)
1. **Origin (COBOL)**: [Brief description of logic/calculation at inception]
2. **Movement & Validation (SSIS)**: [Brief description of ETL pipeline, validations, and staging]
3. **Consumption & Reporting (SQL)**: [Brief description of queries, analytical views, or breakdowns]

### Key Logic & Formulas (Include for calculation/business rule queries; omit if only asking about pipeline flow)
- **[Rule/Calculation Name]**: [Human-readable mathematical equation or business rule with rates, floors, and caps]

### Sources (Omit if question is irrelevant or unverified)
- [Single consolidated list of all verified source file(s) across systems]

CONFIDENCE
[High / Medium / Low — percentage and short rationale]

Answer:
"""

# ── Cypher Repair (fallback) ───────────────────────────────────────────────────
CYPHER_REPAIR_PROMPT = """The following Cypher query failed with the error below.
Fix the Cypher query to make it valid. Return ONLY the corrected Cypher, nothing else.

Original query:
{cypher}

Error:
{error}

Fixed query:
"""