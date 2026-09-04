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
1. ONLY SHOW THE RELEVANT SYSTEM (DO NOT DUMP UNRELATED SYSTEMS):
   - Focus exclusively on the system(s) where the answer ACTUALLY originates:
     • If a calculation takes place in COBOL, show ONLY COBOL. Do NOT include SSIS or SQL just because they query or stage the field.
     • If an ETL data movement takes place in SSIS, show ONLY SSIS. Do NOT include COBOL or SQL unless they are direct sources/destinations of that ETL.
     • If a database query or schema exists in SQL, show ONLY SQL.
   - Merely passing, staging, or selecting a value is NOT calculating it. Never create dummy sections for systems that don't directly perform the asked logic.

2. FORMULAS MUST BE HUMAN-READABLE MATHEMATICAL EQUATIONS (NO RAW CODE DUMPS):
   - Express all calculations as clean mathematical equations using standard business names:
     • Example: `Written Premium = Base ($100.00) + (0.2% × Property Value) + (0.1% × Coverage Limit) − Deductible Discount`
     • DO NOT dump raw code statements or internal variables like `WS-DISCOUNT = WS-DEDUCT-TOTAL * WS-HO-DED-RATE` or SQL `CASE WHEN ...` blocks.
   - Include constants, percentages, minimum floors, and caps directly in the equation.
   - Translate internal code variables into their plain business meaning (e.g. `Property Value` instead of `WS-RISK-VALUE`, `Elapsed Days` instead of `WS-EARNED-DAYS`).

3. CONCISE & TARGETED FORMAT:
   - Provide only the sections needed to answer the question:
     - **ANSWER**: Direct, 1-2 paragraph executive summary.
     - **FORMULA** (only if asking for a calculation): The exact mathematical equation.
     - **DATA FLOW** (only if asking for a pipeline/movement): Concise flow: Input → Processing → Output.
     - **SOURCES**: The exact file name(s) where the logic lives.
   - Do NOT repeat the same subsections (Key Points, Data Flow, Formula, Sources) for multiple systems if only one system is relevant.

4. ZERO HALLUCINATION:
   - Base every statement strictly on the provided evidence. Never invent rules or parameters.

5. NO SOURCES FOR IRRELEVANT OR UNVERIFIED QUESTIONS:
   - If the question is off-topic, not relevant, or no verified evidence exists in the retrieved context:
     • State clearly in the ANSWER section that no relevant evidence exists in the indexed legacy codebase.
     • DO NOT output any system subsections (## COBOL, ## SQL, ## SSIS), formulas, or Sources.
     • Omit the Sources section completely. Never list unrelated or dummy source files.

REQUIRED OUTPUT STRUCTURE:

ANSWER
[Direct, concise answer answering the user's question directly]

## <RELEVANT SYSTEM ONLY (e.g. COBOL)> (Omit if question is irrelevant or unverified)
### Key Logic & Rules
- [Key business rules or logic items]

### Formula (Omit if question does not involve a calculation)
[Clean, human-readable mathematical equation with all rates, floors, and caps]

### Sources (Omit if question is irrelevant or unverified)
- [Exact source file(s) where this logic resides]

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