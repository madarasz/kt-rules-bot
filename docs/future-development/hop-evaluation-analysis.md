# Hop Evaluation Analysis Feature - Implementation Plan

**Status**: Planning
**Created**: 2025-01-26
**Estimated Effort**: 12-15 hours
**Priority**: Medium

## Executive Summary

Implement automated analysis of RAG test hop evaluation failures using LLM to identify generic issues and suggest prompt improvements. The analysis will help tune the hop evaluation prompt without overfitting to specific test queries.

## Problem Statement

### Current State
- Multi-hop retrieval uses LLM to evaluate if context is sufficient (`can_answer`)
- When context is insufficient, hop evaluator suggests `missing_query` for next hop
- RAG tests show some ground truth contexts are never retrieved despite multiple hops
- No systematic way to analyze WHY hop evaluations fail or how to improve them

### Critical Challenge
**Ground truth contexts lack rule location metadata**. A missing chunk like "Place Marker (1AP)" doesn't specify WHERE it should be found in the rules hierarchy. Without this, we cannot meaningfully analyze if hop evaluations generated appropriate `missing_query` values.

**Example**:
```yaml
test_id: banner-carrier-dies
query: "If my plant banner is picked up by my opponent and the carrier dies, who places the banner?"
ground_truth_contexts:
  - "PLANT BANNER"          # Found in: Rules > Tacops > Security
  - "Place Marker (1AP)"     # Found in: Rules 2 Actions > PLACE MARKER
                             # ^^^ THIS LOCATION INFO IS MISSING ^^^
```

If hop evaluation generated `missing_query: "Plant Banner TacOp"`, we can't tell if this was appropriate without knowing "Place Marker" is a core action, not part of the TacOp.

### Success Criteria
- [x] Identify patterns in hop evaluation failures across test runs
- [x] Provide generic (not query-specific) suggestions for prompt improvements
- [x] Store analysis results in database and display on admin dashboard
- [x] Make LLM model for analysis parametrizable
- [x] Enrich missing chunks with rule location information

## Solution Design

### Architecture Overview

```
RAG Test Results (with failures)
    ↓
Extract Missing Chunks + Hop Evaluations
    ↓
Rule Location Resolver → Lookup chunk locations in rules-structure.yml
    ↓
Deduplicate by (chunk, location) → Group queries
    ↓
Hop Evaluation Analyzer (LLM)
    ├─ Input: Missing chunks with locations, hop evals, current prompt, rules structure
    └─ Output: Generic issues + prompt improvement suggestions
    ↓
Save to File + Database
    ↓
Display on Admin Dashboard
```

### Data Flow

```python
# Input: RAG Test Results
results: list[RAGTestResult] = [
    RAGTestResult(
        test_id="banner-carrier-dies",
        query="If banner carrier dies, who places banner?",
        missing_chunks=["Place Marker (1AP)"],
        hop_evaluations=[
            {
                "hop_number": 1,
                "can_answer": False,
                "reasoning": "Missing Plant Banner TacOp rules",
                "missing_query": "Plant Banner TacOp"
            }
        ]
    ),
    # ... more results
]

# Step 1: Extract & Enrich
analyzer = HopEvaluationAnalyzer()
hop_inputs = []

for result in results:
    if not result.missing_chunks:
        continue

    for missing_chunk in result.missing_chunks:
        # Resolve rule location
        rule_section = rule_resolver.find_section(missing_chunk)
        # → "Rules 2 Actions > PLACE MARKER (1AP)"

        hop_inputs.append(HopAnalysisInput(
            missing_chunk=missing_chunk,
            rule_section=rule_section,
            query=result.query,
            hop_evaluations=result.hop_evaluations
        ))

# Step 2: Deduplicate
grouped = group_by_chunk_and_section(hop_inputs)
# {
#   ("Place Marker (1AP)", "Rules 2 Actions"): [
#       (query1, hop_eval1),
#       (query2, hop_eval2)
#   ]
# }

# Step 3: Analyze
analysis = analyzer.analyze(
    grouped_inputs=grouped,
    current_hop_prompt=load_prompt("hop-evaluation-prompt.md"),
    rules_structure=load_yaml("rules-structure.yml")
)

# Step 4: Save
save_to_file(analysis, "results/{timestamp}/hop_analysis.txt")
db.update_rag_test_run(run_id, hop_analysis_report=analysis)
```

## Implementation Phases

### Phase 1: Rule Location Resolver (2-3 hours)

**Objective**: Given a chunk header, find where it lives in rules-structure.yml

**File**: `src/services/rag/rule_location_resolver.py`

**API Design**:
```python
class RuleLocationResolver:
    def __init__(self):
        self.rules_structure = load_yaml(RULES_STRUCTURE_PATH)
        self.teams_structure = load_yaml(TEAMS_STRUCTURE_PATH)

    def find_section(self, chunk_header: str) -> str:
        """Find section path for chunk header.

        Returns:
            Section path like "Rules 2 Actions > DASH (1AP)"
            Or "Unknown" if not found
        """
        # Search rules structure
        path = self._search_structure(chunk_header, self.rules_structure)
        if path:
            return " > ".join(path)

        # Search teams structure
        path = self._search_structure(chunk_header, self.teams_structure)
        if path:
            return " > ".join(["Teams"] + path)

        return "Unknown"

    def _search_structure(self, header: str, structure: dict, path: list[str] = None) -> list[str] | None:
        """Recursively search YAML structure for header."""
        # Implementation: traverse YAML, match chunk headers
```

**Challenges**:
- Chunk headers might be substrings (e.g., "DASH" vs "DASH (1AP)")
- Multiple matches possible (handle gracefully)
- Performance (cache loaded YAMLs)

**Testing**:
```python
resolver = RuleLocationResolver()
assert resolver.find_section("DASH (1AP)") == "Rules 2 Actions > DASH (1AP)"
assert resolver.find_section("PLANT BANNER") == "Approved Ops 2025 > Tacops > Security > PLANT BANNER"
```

---

### Phase 2: Data Models & Extraction (2 hours)

**Objective**: Define data structures and extract failed tests

**File**: `tests/rag/test_case_models.py`

**New Models**:
```python
@dataclass
class QueryHopPair:
    """Single query that missed this chunk."""
    query: str
    hop_evaluations: list[dict]  # Hop eval dicts from RAGTestResult
    test_id: str

@dataclass
class HopAnalysisInput:
    """Grouped missing chunks for analysis."""
    missing_chunk: str
    rule_section: str  # From RuleLocationResolver
    occurrences: list[QueryHopPair]  # All queries that missed this chunk
    occurrence_count: int  # How many times this chunk was missed

@dataclass
class HopAnalysisResult:
    """Analysis output."""
    analysis_text: str  # Plain text markdown analysis
    model: str  # LLM model used
    timestamp: str  # ISO timestamp
```

**Extraction Logic**:
```python
def extract_hop_analysis_inputs(
    results: list[RAGTestResult],
    rule_resolver: RuleLocationResolver
) -> list[HopAnalysisInput]:
    """Extract and deduplicate missing chunks with hop evaluations."""

    # Collect all missing chunks with context
    chunk_map: dict[tuple[str, str], list[QueryHopPair]] = defaultdict(list)

    for result in results:
        if not result.missing_chunks:
            continue

        for missing_chunk in result.missing_chunks:
            rule_section = rule_resolver.find_section(missing_chunk)
            key = (missing_chunk, rule_section)

            chunk_map[key].append(QueryHopPair(
                query=result.query,
                hop_evaluations=result.hop_evaluations or [],
                test_id=result.test_id
            ))

    # Convert to list
    return [
        HopAnalysisInput(
            missing_chunk=chunk,
            rule_section=section,
            occurrences=queries,
            occurrence_count=len(queries)
        )
        for (chunk, section), queries in chunk_map.items()
    ]
```

---

### Phase 3: Analysis Service & Prompt (3-4 hours)

**Objective**: Core analysis logic and LLM prompt

**File 1**: `src/services/rag/hop_evaluation_analyzer.py`

```python
class HopEvaluationAnalyzer:
    """Analyzes hop evaluation failures and suggests improvements."""

    def __init__(self, model: str = HOP_ANALYSIS_LLM_MODEL):
        self.model = model
        self.rule_resolver = RuleLocationResolver()
        self.llm_provider = LLMProviderFactory.create(model)

    async def analyze(
        self,
        results: list[RAGTestResult],
        run_id: str
    ) -> HopAnalysisResult:
        """Analyze hop evaluation failures."""

        # Extract missing chunks with locations
        inputs = extract_hop_analysis_inputs(results, self.rule_resolver)

        if not inputs:
            return HopAnalysisResult(
                analysis_text="No missing chunks found. All tests passed!",
                model=self.model,
                timestamp=datetime.now(UTC).isoformat()
            )

        # Load current hop prompt
        current_prompt = self._load_hop_prompt()

        # Load rules structure
        rules_structure = self._load_rules_structure()

        # Format analysis prompt
        analysis_prompt = self._format_analysis_prompt(
            inputs=inputs,
            current_hop_prompt=current_prompt,
            rules_structure=rules_structure
        )

        # Call LLM (no structured output)
        response = await self.llm_provider.generate(
            prompt=analysis_prompt,
            max_tokens=HOP_ANALYSIS_MAX_TOKENS,
            temperature=0.1
        )

        return HopAnalysisResult(
            analysis_text=response,
            model=self.model,
            timestamp=datetime.now(UTC).isoformat()
        )
```

**File 2**: `prompts/hop-evaluation-analysis-prompt.md`

```markdown
# Hop Evaluation Analysis Task

You are analyzing failures in a multi-hop RAG retrieval system for Kill Team game rules. Your goal is to identify **generic patterns** in hop evaluation failures and suggest **generic improvements** to the hop evaluation prompt.

## Context

### System Overview
- Users ask Kill Team rules questions
- System retrieves relevant rule chunks from vector database
- If context is insufficient, a "hop evaluator" LLM assesses what's missing
- Hop evaluator generates a `missing_query` to retrieve additional context
- Process repeats until context is sufficient or max hops reached

### Current Hop Evaluation Prompt
```
{current_hop_prompt}
```

### Rules Structure (for reference)
```yaml
{rules_structure_summary}
```

## Data: Missing Chunks Analysis

Below are ground truth rule chunks that were NEVER retrieved despite hop evaluations. Each chunk includes:
- **Chunk Header**: The rule section that was missed
- **Rule Section**: WHERE in the rules hierarchy this chunk lives
- **Occurrences**: How many times it was missed (X times)
- **Example Queries**: Sample user queries that needed this chunk
- **Hop Evaluations**: What the hop evaluator said (can_answer=False, reasoning, missing_query)

{formatted_missing_chunks}

## Your Task

Analyze the above data and provide:

1. **Generic Issues Identified** (2-4 bullet points)
   - Patterns across multiple missing chunks
   - Structural problems in hop evaluation logic
   - Categories of rules frequently missed (e.g., "actions", "terrain", "core rules")

2. **Suggested Prompt Improvements** (2-4 concrete suggestions)
   - Changes to hop evaluation prompt structure
   - Additional instructions or decision trees
   - Improvements to `missing_query` generation logic

## CRITICAL CONSTRAINTS

❌ **DO NOT**:
- Include specific test queries as examples in your suggestions
- Suggest adding "if query mentions X" logic (too specific)
- Propose solutions that only fix one test case

✅ **DO**:
- Focus on generic patterns (e.g., "action-related rules often missed")
- Suggest structural prompt improvements
- Propose decision trees or categorization logic
- Identify rule hierarchy blind spots

## Output Format

Use markdown with clear sections:

```markdown
## Hop Evaluation Analysis Report

**Run ID**: {run_id}
**Analysis Model**: {model}
**Timestamp**: {timestamp}
**Total Unique Missing Chunks**: X
**Total Test Failures Analyzed**: Y

### Generic Issues Identified

1. **[Issue Category]**
   - [Description of pattern]
   - [Evidence from data]

2. **[Issue Category]**
   ...

### Suggested Prompt Improvements

1. **[Improvement Title]**
   - Current: [What the prompt currently does/says]
   - Suggested: [Proposed change]
   - Rationale: [Why this helps]

2. **[Improvement Title]**
   ...

### Additional Observations
- [Any other relevant insights]
```

Now analyze the data and provide your report.
```

**Prompt Formatting Helper**:
```python
def _format_analysis_prompt(self, inputs, current_hop_prompt, rules_structure):
    """Format analysis prompt with data."""

    # Format missing chunks
    formatted_chunks = []
    for inp in inputs:
        chunk_section = f"### {inp.missing_chunk}\n"
        chunk_section += f"**Rule Section**: {inp.rule_section}\n"
        chunk_section += f"**Occurrences**: {inp.occurrence_count} times\n\n"

        # Show first 3 examples (avoid overwhelming LLM)
        for i, occ in enumerate(inp.occurrences[:3]):
            chunk_section += f"**Example {i+1}**:\n"
            chunk_section += f"- Query: \"{occ.query}\"\n"

            if occ.hop_evaluations:
                for hop in occ.hop_evaluations:
                    chunk_section += f"- Hop {hop['hop_number']}: can_answer={hop['can_answer']}\n"
                    chunk_section += f"  - Reasoning: {hop['reasoning']}\n"
                    chunk_section += f"  - Missing Query: {hop.get('missing_query', 'N/A')}\n"
            chunk_section += "\n"

        if inp.occurrence_count > 3:
            chunk_section += f"*...and {inp.occurrence_count - 3} more occurrences*\n\n"

        formatted_chunks.append(chunk_section)

    # Summarize rules structure (don't include full YAML)
    rules_summary = self._summarize_rules_structure(rules_structure)

    # Load prompt template
    template = Path("prompts/hop-evaluation-analysis-prompt.md").read_text()

    return template.format(
        current_hop_prompt=current_hop_prompt,
        rules_structure_summary=rules_summary,
        formatted_missing_chunks="\n".join(formatted_chunks),
        run_id=self.run_id,
        model=self.model,
        timestamp=datetime.now().isoformat()
    )
```

---

### Phase 4: CLI Integration (1 hour)

**Objective**: Add --summary flag to rag-test command

**File 1**: `src/cli/__main__.py`

```python
# Add arguments to rag-test command
rag_parser.add_argument(
    "--summary",
    action="store_true",
    help="Generate hop evaluation analysis summary (requires LLM call)"
)
rag_parser.add_argument(
    "--hop-analysis-model",
    type=str,
    default=HOP_ANALYSIS_LLM_MODEL,
    help=f"LLM model for hop analysis (default: {HOP_ANALYSIS_LLM_MODEL})"
)
```

**File 2**: `src/cli/rag_test.py`

```python
async def rag_test(
    test_id: str | None = None,
    runs: int = 1,
    max_chunks: int = RAG_MAX_CHUNKS,
    min_relevance: float = RAG_MIN_RELEVANCE,
    summary: bool = False,  # NEW
    hop_analysis_model: str = HOP_ANALYSIS_LLM_MODEL,  # NEW
) -> None:
    """Run RAG tests with optional hop evaluation analysis."""

    # ... existing test execution ...

    results, total_time = runner.run_tests(...)
    summary_stats = runner.calculate_summary(...)

    # Generate report
    report_gen.generate_report(results, summary_stats, report_path)

    # NEW: Hop evaluation analysis
    hop_analysis_result = None
    if summary:
        print("\n" + "=" * 80)
        print("GENERATING HOP EVALUATION ANALYSIS")
        print("=" * 80)
        print(f"Using model: {hop_analysis_model}")

        analyzer = HopEvaluationAnalyzer(model=hop_analysis_model)
        hop_analysis_result = await analyzer.analyze(results, timestamp)

        # Save to file
        analysis_path = results_dir / "hop_analysis.txt"
        analysis_path.write_text(hop_analysis_result.analysis_text)

        print(f"\nHop analysis saved to: {analysis_path}")
        print("\nAnalysis Preview:")
        print("-" * 80)
        print(hop_analysis_result.analysis_text[:500] + "...")

    # Save to database
    _save_to_database(
        timestamp,
        summary_stats,
        report_path,
        hop_analysis_result  # NEW: Pass analysis result
    )
```

---

### Phase 5: Database Schema & Migration (2 hours)

**Objective**: Store hop analysis in database

**File 1**: `scripts/migrate_db.py`

```python
def migrate_analytics_db(db_path: str) -> None:
    """Add missing columns to analytics database."""

    # ... existing migrations ...

    migrations = [
        # ... existing migrations ...

        # Hop evaluation analysis columns (added 2025-01-26)
        ("rag_test_runs", "hop_analysis_report", "TEXT DEFAULT NULL"),
        ("rag_test_runs", "hop_analysis_model", "TEXT DEFAULT NULL"),
        ("rag_test_runs", "hop_analysis_timestamp", "TEXT DEFAULT NULL"),
    ]

    # ... rest of migration logic ...
```

**File 2**: `src/lib/database.py`

Update schema:
```python
SCHEMA_SQL = """
...
CREATE TABLE IF NOT EXISTS rag_test_runs (
    run_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    test_set TEXT,
    runs_per_test INTEGER,
    avg_retrieval_time REAL,
    avg_retrieval_cost REAL,
    context_recall REAL,
    avg_hops_used REAL,
    can_answer_recall REAL,
    full_report_md TEXT,
    run_name TEXT DEFAULT '',
    comments TEXT DEFAULT '',
    favorite INTEGER DEFAULT 0,
    hop_analysis_report TEXT DEFAULT NULL,  -- NEW
    hop_analysis_model TEXT DEFAULT NULL,   -- NEW
    hop_analysis_timestamp TEXT DEFAULT NULL,  -- NEW
    created_at TEXT NOT NULL
);
...
"""
```

Update insert method:
```python
def insert_rag_test_run(
    self,
    run_data: dict[str, Any],
    hop_analysis: HopAnalysisResult | None = None  # NEW
) -> None:
    """Insert RAG test run with optional hop analysis."""

    if not self.enabled:
        return

    # Add hop analysis fields
    if hop_analysis:
        run_data["hop_analysis_report"] = hop_analysis.analysis_text
        run_data["hop_analysis_model"] = hop_analysis.model
        run_data["hop_analysis_timestamp"] = hop_analysis.timestamp

    # ... rest of insert logic ...
```

---

### Phase 6: Admin Dashboard Display (2-3 hours)

**Objective**: Show hop analysis prominently on RAG Test Results page

**File**: `src/admin_dashboard/pages/rag_test_results.py`

```python
def render(db: AnalyticsDatabase) -> None:
    """Render RAG test results page."""

    st.title("📊 RAG Test Results")

    # NEW: Hop Analysis Insights Section
    _render_hop_analysis_insights(db)

    st.divider()

    # Existing: Test runs table
    test_runs = db.get_all_rag_test_runs(limit=100)
    # ... existing rendering logic ...


def _render_hop_analysis_insights(db: AnalyticsDatabase) -> None:
    """Render hop analysis insights at top of page."""

    # Get most recent test run with analysis
    test_runs = db.get_all_rag_test_runs(limit=10)
    runs_with_analysis = [
        run for run in test_runs
        if run.get("hop_analysis_report")
    ]

    if not runs_with_analysis:
        st.info("💡 Run RAG tests with `--summary` flag to generate hop evaluation analysis")
        return

    # Show latest analysis
    latest = runs_with_analysis[0]

    with st.expander("🔍 Hop Evaluation Analysis Insights", expanded=True):
        st.markdown(f"**Latest Analysis**: {latest['run_name'] or latest['run_id']}")
        st.caption(f"Model: {latest['hop_analysis_model']} | "
                  f"Generated: {latest['hop_analysis_timestamp']}")

        st.markdown("---")
        st.markdown(latest["hop_analysis_report"])

        # Show historical analyses
        if len(runs_with_analysis) > 1:
            with st.expander("📜 View All Analyses"):
                for run in runs_with_analysis[1:]:
                    st.markdown(f"### {run['run_name'] or run['run_id']}")
                    st.caption(f"{run['hop_analysis_timestamp']}")
                    st.text(run["hop_analysis_report"][:300] + "...")

                    if st.button(f"View Full Analysis", key=f"view_{run['run_id']}"):
                        st.markdown(run["hop_analysis_report"])
```

**Styling**:
- Use warning color for "Issues Identified" section
- Use success color for "Suggestions" section
- Collapsible by default (can expand)

---

### Phase 7: Configuration Constants (30 minutes)

**File**: `src/lib/constants.py`

```python
# ============================================================================
# Hop Evaluation Analysis Constants
# ============================================================================

# LLM model for analyzing hop evaluation failures (default: GPT-4o)
HOP_ANALYSIS_LLM_MODEL = "gpt-4o"

# Analysis generation timeout (seconds)
HOP_ANALYSIS_TIMEOUT = 60

# Max tokens for analysis output (longer text needed)
HOP_ANALYSIS_MAX_TOKENS = 4000

# Temperature for analysis (low for consistency)
HOP_ANALYSIS_TEMPERATURE = 0.1
```

Update imports in relevant files to use these constants.

---

### Phase 8: Testing & Validation (2 hours)

**Test Plan**:

1. **Unit Tests** (`tests/unit/services/rag/test_rule_location_resolver.py`):
   ```python
   def test_find_section_actions():
       resolver = RuleLocationResolver()
       assert resolver.find_section("DASH (1AP)") == "Rules 2 Actions > DASH (1AP)"

   def test_find_section_tacop():
       resolver = RuleLocationResolver()
       assert "PLANT BANNER" in resolver.find_section("PLANT BANNER")

   def test_find_section_unknown():
       resolver = RuleLocationResolver()
       assert resolver.find_section("NONEXISTENT RULE") == "Unknown"
   ```

2. **Integration Test**:
   ```bash
   # Run RAG tests with analysis
   python -m src.cli rag-test --runs 3 --summary

   # Verify:
   # - hop_analysis.txt created in results dir
   # - Analysis is generic (no query-specific examples)
   # - Database has hop_analysis_report populated
   # - Dashboard displays analysis
   ```

3. **Manual Validation**:
   - Review analysis output for quality
   - Check that suggestions are actionable
   - Verify rule location lookups are accurate
   - Test with different LLM models (gpt-4o, claude-4.5-sonnet)

4. **Migration Test**:
   ```bash
   # Test on existing database
   python3 scripts/migrate_db.py

   # Verify:
   # - New columns added without data loss
   # - Indexes created
   # - No errors
   ```

---

## File Changes Summary

### Files to Create (5 new files)
1. `src/services/rag/rule_location_resolver.py` - Lookup chunk → rule section
2. `src/services/rag/hop_evaluation_analyzer.py` - Analysis service
3. `prompts/hop-evaluation-analysis-prompt.md` - LLM prompt
4. `tests/unit/services/rag/test_rule_location_resolver.py` - Unit tests
5. `docs/future-development/hop-evaluation-analysis.md` - This document

### Files to Modify (7 files)
1. `src/cli/__main__.py` - Add `--summary` flag + `--hop-analysis-model` param
2. `src/cli/rag_test.py` - Integrate analyzer, save results
3. `src/lib/database.py` - Add hop_analysis columns + methods, update schema
4. `src/lib/constants.py` - Add HOP_ANALYSIS_* constants
5. `scripts/migrate_db.py` - Add migration for new columns
6. `src/admin_dashboard/pages/rag_test_results.py` - Display analysis section
7. `tests/rag/test_case_models.py` - Add `HopAnalysisInput`, `HopAnalysisResult` dataclasses

### Database Schema Changes
```sql
-- Migration in scripts/migrate_db.py
ALTER TABLE rag_test_runs ADD COLUMN hop_analysis_report TEXT DEFAULT NULL;
ALTER TABLE rag_test_runs ADD COLUMN hop_analysis_model TEXT DEFAULT NULL;
ALTER TABLE rag_test_runs ADD COLUMN hop_analysis_timestamp TEXT DEFAULT NULL;
```

---

## Expected Output Example

```markdown
## Hop Evaluation Analysis Report

**Run ID**: 20250126_143022
**Analysis Model**: gpt-4o
**Timestamp**: 2025-01-26T14:30:22.123456
**Total Unique Missing Chunks**: 8
**Total Test Failures Analyzed**: 15

### Generic Issues Identified

1. **Core Action Rules Frequently Missed**
   - Chunks from "Rules 2 Actions" section missed in 6/15 test failures
   - Hop evaluations focused on abilities/ploys, not core actions
   - Example: "Place Marker (1AP)" missed when query involved TacOps
   - Evidence: Hop missing_query values like "Plant Banner TacOp" don't retrieve action definitions

2. **Killzone-Specific Rules Overlooked**
   - Terrain features from "Killzone" section missed in 4/15 failures
   - Hop evaluations generated generic queries like "terrain rules"
   - Specific killzone rules (Gallowdark, Volkus) not targeted
   - Suggests hop evaluator lacks awareness of killzone-specific mechanics

3. **Multi-Hop Queries Too Narrow**
   - When context includes partial info, hop missing_query is too focused
   - Example: Query about "banner carrier dying" missed "Place Marker" action
   - Hop focused on TacOp, didn't recognize action prerequisite

### Suggested Prompt Improvements

1. **Expand "List of Terms" Step to Include Actions & Terrain**
   - **Current**: "Identify all operative names, abilities, keywords, and rule definitions"
   - **Suggested**: "Identify all operative names, abilities, keywords, **actions** (Move, Shoot, Place Marker, etc.), **terrain features** (Vantage, Heavy, killzone-specific), and rule definitions"
   - **Rationale**: Explicitly prompting for actions and terrain will reduce blind spots in these categories

2. **Add Rule Hierarchy Decision Tree**
   - **Current**: Single evaluation step for missing context
   - **Suggested**: Add structured decision tree:
     ```
     If question involves operative abilities → check Teams section
     If question involves movement/shooting/placing → check Actions section
     If question involves terrain/cover/killzones → check Killzone section
     If question involves TacOps/Critops → check Approved Ops section
     ```
   - **Rationale**: Guides hop evaluator to target correct rule hierarchy sections

3. **Improve Missing Query Specificity**
   - **Current**: No guidance on missing_query format
   - **Suggested**: Add instruction: "When generating missing_query, use specific rule/ability/action names from the rules structure, not generic terms. Example: Use 'Vantage terrain' not 'terrain rules', use 'Place Marker action' not 'marker placement'."
   - **Rationale**: More specific queries improve BM25 keyword matching

4. **Add Context Dependency Check**
   - **Current**: Evaluates context in isolation
   - **Suggested**: Add instruction: "Consider if the question requires multiple related rules. If context covers ability X but question asks about interaction with Y, you may need BOTH definitions even if one is present."
   - **Rationale**: Prevents premature can_answer=True when partial context exists

### Additional Observations

- Average hops used: 0.6 (suggests early termination)
- Hop recall: 65% (room for improvement)
- Most failures occurred in tests involving TacOps + Actions interactions
- Consider increasing RAG_MAX_HOPS to 2 for better coverage

---

**Note**: All suggestions are generic and do not reference specific test queries. Implementation should focus on prompt structure improvements, not test-specific fixes.
```

---

## Key Design Decisions

### ✅ Design Choices

1. **Rule Location Lookup at Analysis Time**
   - **Why**: Avoids modifying test runner, keeps concerns separated
   - **Trade-off**: Slight redundant work (lookup multiple times if chunk missed multiple times)
   - **Acceptable**: Analysis is infrequent (only with --summary flag)

2. **Parametrizable Analysis Model**
   - **Why**: Different models have different strengths (GPT-4o vs Claude)
   - **Default**: GPT-4o for strong reasoning
   - **Override**: `--hop-analysis-model` flag

3. **Plain Text Output (Not Structured)**
   - **Why**: Analysis is for human review, not programmatic processing
   - **Benefit**: More natural language, flexible format
   - **Trade-off**: Can't automatically apply suggestions (future enhancement)

4. **Deduplication by (Chunk, Location)**
   - **Why**: Same chunk in different locations = different failure modes
   - **Example**: "MOVE" could appear in "Rules 2 Actions" and "Killzone Gallowdark"
   - **Benefit**: More granular analysis

5. **Only Run with --summary Flag**
   - **Why**: Analysis requires LLM call (cost), not always needed
   - **Default**: Off (opt-in)
   - **Use Case**: Periodic deep dives, not every test run

6. **Store in rag_test_runs Table**
   - **Why**: Analysis is metadata about a test run
   - **Alternative**: Separate table (rejected: overkill for MVP)
   - **Benefit**: Simple query, joins not needed

### ❌ Rejected Alternatives

1. **Store Rule Locations During Ingestion**
   - **Why Rejected**: Would require chunking changes, metadata overhead
   - **Chosen Instead**: Lookup at analysis time (acceptable performance)

2. **Structured Output with Auto-Apply**
   - **Why Rejected**: Complex, risky to auto-modify prompts
   - **Chosen Instead**: Human-reviewed suggestions, manual application

3. **Separate Analysis Command**
   - **Why Rejected**: Adds CLI complexity
   - **Chosen Instead**: --summary flag (simpler UX)

4. **Store Analysis Per Test Case**
   - **Why Rejected**: Analysis is aggregate, not per-test
   - **Chosen Instead**: Store at run level

---

## Risks & Mitigations

### 🔴 High Risk: Rule Location Lookup Failures

**Risk**: RuleLocationResolver can't find some chunks
**Impact**: Analysis missing context, less useful
**Mitigation**:
- Fuzzy matching (Levenshtein distance)
- Manual fallback list for common chunks
- Log "Unknown" locations for investigation
- Display "Unknown location" in analysis (prompts manual review)

### 🟡 Medium Risk: LLM Provides Query-Specific Examples

**Risk**: Despite instructions, LLM includes test queries in suggestions
**Impact**: Overfitting, unfair test improvements
**Mitigation**:
- Strong prompt language ("CRITICAL CONSTRAINT: DO NOT...")
- Post-processing check (regex for query patterns)
- Human review before applying suggestions
- Test with multiple models (GPT-4o less likely than others)

### 🟡 Medium Risk: Analysis Too Generic to Be Actionable

**Risk**: LLM suggestions are vague ("improve prompt clarity")
**Impact**: Wasted effort, no concrete improvements
**Mitigation**:
- Provide rich context (rules structure, hop eval details)
- Prompt for concrete changes ("Current: ... Suggested: ...")
- Show examples of good vs bad missing_query values

### 🟢 Low Risk: Performance Degradation

**Risk**: Analysis takes too long, blocks test workflow
**Impact**: User frustration
**Mitigation**:
- Optional flag (--summary), doesn't block default workflow
- Timeout (60s default)
- Async execution (doesn't block report generation)

---

## Future Enhancements

### Phase 2 Features (Post-MVP)

1. **Auto-Apply Suggestions**
   - Parse structured suggestions
   - Generate diff for hop-evaluation-prompt.md
   - Run A/B test: old prompt vs new prompt
   - Compare hop recall metrics

2. **Rule Coverage Analysis**
   - Track which rule sections are frequently missed
   - Heatmap: Rules Structure × Miss Frequency
   - Identify "blind spot" sections

3. **Chunk → Rule Mapping in ChromaDB**
   - Add rule_section to chunk metadata during ingestion
   - Eliminates need for RuleLocationResolver
   - Enables filtering: "Only retrieve from Rules 2 Actions"

4. **Historical Trend Analysis**
   - Compare hop recall over multiple test runs
   - Detect regressions after prompt changes
   - Dashboard: "Hop Recall Over Time" chart

5. **Interactive Prompt Tuning**
   - Streamlit UI: Edit hop prompt inline
   - Click "Test Changes" → runs RAG tests
   - Compare before/after metrics

---

## Success Metrics

### Immediate (Post-Implementation)
- [x] Feature ships without bugs
- [x] Analysis generates for test runs with failures
- [x] Dashboard displays analysis correctly
- [x] Migration succeeds on existing databases

### Short-Term (1-2 weeks)
- [ ] Human review confirms suggestions are generic
- [ ] At least 2 actionable prompt improvements identified
- [ ] Apply 1-2 suggestions, re-run tests, measure impact

### Long-Term (1-2 months)
- [ ] Hop can_answer_recall improves by 10%+
- [ ] Fewer manual test failures due to missing chunks
- [ ] Prompt improvements reduce "Unknown" rule locations

---

## Documentation Updates

### Update CLAUDE.md Files

1. **src/services/rag/CLAUDE.md**
   - Add section on `RuleLocationResolver`
   - Add section on `HopEvaluationAnalyzer`
   - Explain when to use --summary flag

2. **src/cli/CLAUDE.md**
   - Document `--summary` flag for rag-test
   - Document `--hop-analysis-model` parameter
   - Show example usage

3. **Root CLAUDE.md**
   - Brief mention in "Common Agent Tasks" section

### Update Admin Dashboard Guide

- Add screenshot of Hop Analysis Insights section
- Explain how to interpret analysis reports
- Workflow: Run tests → Review analysis → Apply suggestions → Re-test

---

## Timeline Estimate

| Phase | Task | Hours | Cumulative |
|-------|------|-------|------------|
| 1 | Rule Location Resolver | 2-3h | 2-3h |
| 2 | Data Models & Extraction | 2h | 4-5h |
| 3 | Analysis Service & Prompt | 3-4h | 7-9h |
| 4 | CLI Integration | 1h | 8-10h |
| 5 | Database Schema & Migration | 2h | 10-12h |
| 6 | Admin Dashboard Display | 2-3h | 12-15h |
| 7 | Configuration Constants | 0.5h | 12.5-15.5h |
| 8 | Testing & Validation | 2h | 14.5-17.5h |

**Total Estimated Effort**: 12-15 hours (conservative estimate)

**Breakdown by Complexity**:
- Simple: 3.5h (CLI, config)
- Medium: 6-7h (models, database, dashboard)
- Complex: 5-7h (rule resolver, analyzer, prompt)

---

## Appendix: Example Data Structures

### RuleLocationResolver Example

```python
# Input: Chunk header
chunk = "DASH (1AP)"

# Output: Rule section path
resolver = RuleLocationResolver()
section = resolver.find_section(chunk)
# → "Rules 2 Actions > DASH (1AP)"
```

### HopAnalysisInput Example

```python
HopAnalysisInput(
    missing_chunk="Place Marker (1AP)",
    rule_section="Rules 2 Actions > PLACE MARKER (1AP)",
    occurrences=[
        QueryHopPair(
            query="If banner carrier dies, who places banner?",
            hop_evaluations=[
                {
                    "hop_number": 1,
                    "can_answer": False,
                    "reasoning": "Missing Plant Banner TacOp rules",
                    "missing_query": "Plant Banner TacOp"
                }
            ],
            test_id="banner-carrier-dies"
        ),
        QueryHopPair(
            query="Can I place a marker during conceal?",
            hop_evaluations=[
                {
                    "hop_number": 1,
                    "can_answer": False,
                    "reasoning": "Need conceal order restrictions",
                    "missing_query": "Conceal order actions"
                }
            ],
            test_id="conceal-place-marker"
        )
    ],
    occurrence_count=2
)
```

---

## Questions & Answers

**Q: Why not store rule locations during chunking/ingestion?**
A: That would require modifying the ingestion pipeline and adding metadata to every chunk. This approach (lookup at analysis time) is simpler and doesn't affect core retrieval performance. Analysis is infrequent (only with --summary), so the redundant lookups are acceptable.

**Q: What if RuleLocationResolver can't find a chunk?**
A: It returns "Unknown" and logs the failure. The analysis will include "Unknown location" for those chunks, prompting manual investigation. We can maintain a fallback mapping for common chunks if needed.

**Q: How do we prevent overfitting to specific test queries?**
A: Strong prompt instructions + human review. The prompt explicitly forbids query-specific examples. Before applying suggestions, a human reviews them to ensure they're generic structural improvements.

**Q: Can we auto-apply the suggested prompt changes?**
A: Not in MVP. Analysis output is plain text for human review. Auto-apply could be added as Phase 2 enhancement with structured output and A/B testing.

**Q: What's the cost of running --summary?**
A: Depends on model and failure count. Estimate:
- GPT-4o: ~$0.01-0.05 per analysis (4K input tokens, 2K output)
- Claude Sonnet: ~$0.008-0.04 per analysis
- Acceptable for periodic deep dives, not every test run.

**Q: How often should we run --summary?**
A: Weekly or after major prompt changes. Not needed for every test run during development.

---

## References

- [Multi-Hop RAG Documentation](docs/future-development/MULTI-HOP-IMPROVEMENTS.md)
- [RAG Testing Documentation](tests/rag/CLAUDE.md)
- [Hop Evaluation Prompt](prompts/hop-evaluation-prompt-with-rule-reference.md)
- [Rules Structure](extracted-rules/rules-structure.yml)

---

**Status**: Ready for implementation
**Next Step**: Review plan with team, get approval, start Phase 1
