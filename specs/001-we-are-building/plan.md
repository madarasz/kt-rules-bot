
# Implementation Plan: Kill Team Rules Discord Bot

**Branch**: `001-we-are-building` | **Date**: 2025-10-02 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-we-are-building/spec.md`

## Execution Flow (/plan command scope)
```
1. Load feature spec from Input path
   → If not found: ERROR "No feature spec at {path}"
2. Fill Technical Context (scan for NEEDS CLARIFICATION)
   → Detect Project Type from file system structure or context (web=frontend+backend, mobile=app+api)
   → Set Structure Decision based on project type
3. Fill the Constitution Check section based on the content of the constitution document.
4. Evaluate Constitution Check section below
   → If violations exist: Document in Complexity Tracking
   → If no justification possible: ERROR "Simplify approach first"
   → Update Progress Tracking: Initial Constitution Check
5. Execute Phase 0 → research.md
   → If NEEDS CLARIFICATION remain: ERROR "Resolve unknowns"
6. Execute Phase 1 → contracts, data-model.md, quickstart.md, agent-specific template file (e.g., `CLAUDE.md` for Claude Code, `.github/copilot-instructions.md` for GitHub Copilot, `GEMINI.md` for Gemini CLI, `QWEN.md` for Qwen Code or `AGENTS.md` for opencode).
7. Re-evaluate Constitution Check section
   → If new violations: Refactor design, return to Phase 1
   → Update Progress Tracking: Post-Design Constitution Check
8. Plan Phase 2 → Describe task generation approach (DO NOT create tasks.md)
9. STOP - Ready for /tasks command
```

**IMPORTANT**: The /plan command STOPS at step 7. Phases 2-4 are executed by other commands:
- Phase 2: /tasks command creates tasks.md
- Phase 3-4: Implementation execution (manual or via tools)

## Summary
Discord bot for Kill Team 3rd edition rules assistance using RAG (Retrieval-Augmented Generation). Bot responds to @ mentions with rule citations from markdown knowledge base. Automated PDF ingestion pipeline updates rules. LLM-agnostic architecture with configurable model providers (Claude, Gemini, ChatGPT).

## Technical Context
**Language/Version**: Python 3.11+
**Primary Dependencies**: discord.py (Discord API), LangChain/LlamaIndex (RAG framework), vector database (Chroma/Pinecone/Weaviate), PyPDF2/pdfplumber (PDF extraction), configurable LLM providers (Anthropic/OpenAI/Google APIs)
**Storage**: Vector database for embeddings, filesystem for markdown rules (extracted-rules/), metadata store for document versions
**Testing**: pytest (unit/integration), pytest-asyncio (Discord async testing), contract testing for RAG pipeline
**Target Platform**: Linux server (Docker container), Python runtime
**Project Type**: single (backend service with CLI tools)
**Performance Goals**: <30 seconds response latency, 5 concurrent users, RAG precision ≥90% / recall ≥70%
**Constraints**: Discord API rate limits, GDPR compliance (1-week data retention), token usage budget monitoring
**Scale/Scope**: Single Discord bot instance, 12 initial markdown documents, ~50-100 daily queries expected

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**I. Test-First Development**:
- [x] Test strategy defined (unit, integration, contract, e2e)
- [x] TDD workflow enforced (tests before implementation)
- [x] Acceptance criteria includes test scenarios

**II. LLM Model Independence**:
- [x] LLM interactions abstracted behind interfaces
- [x] No provider-specific business logic
- [x] Model selection configurable

**III. Security by Design**:
- [x] Input validation strategy defined
- [x] Secrets management approach documented
- [x] Rate limiting and abuse prevention planned
- [x] Security logging requirements identified

**IV. RAG Data Integrity**:
- [x] Document ingestion validation planned
- [x] Embedding versioning strategy defined
- [x] Retrieval quality metrics identified
- [x] Source traceability implemented

**V. Observable and Debuggable**:
- [x] Structured logging with correlation IDs
- [x] LLM interaction logging (with PII redaction)
- [x] Performance metrics defined
- [x] Health check endpoints planned

**VI. Automated Quality Gates**:
- [x] Functional test automation planned (80%+ coverage)
- [x] Code quality metrics defined (complexity, duplication, maintainability)
- [x] Security scanning integrated (dependencies, secrets, SAST)
- [x] Performance benchmarks established (latency, token usage)
- [x] CI/CD pipeline gates configured

## Project Structure

### Documentation (this feature)
```
specs/001-we-are-building/
├── plan.md              # This file (/plan command output)
├── research.md          # Phase 0 output (/plan command)
├── data-model.md        # Phase 1 output (/plan command)
├── quickstart.md        # Phase 1 output (/plan command)
├── contracts/           # Phase 1 output (/plan command)
└── tasks.md             # Phase 2 output (/tasks command - NOT created by /plan)
```

### Source Code (repository root)
```
src/
├── models/              # Data models (User Query, Rule Document, Bot Response, etc.)
├── services/            # Core services (RAG, Discord bot, PDF ingestion, LLM adapters)
│   ├── rag/            # RAG retrieval engine
│   ├── discord/        # Discord bot integration
│   ├── llm/            # LLM provider adapters (Claude, Gemini, ChatGPT)
│   └── ingestion/      # PDF download and markdown extraction
├── cli/                # CLI tools for admin tasks (ingest PDFs, test queries)
└── lib/                # Shared utilities (logging, config, validation)

tests/
├── contract/           # RAG pipeline contracts, LLM adapter contracts
├── integration/        # Discord bot flows, PDF ingestion end-to-end
└── unit/               # Individual component tests

extracted-rules/        # Markdown knowledge base (existing, 12 files)
config/                 # Configuration templates (LLM API keys, Discord token)
```

**Structure Decision**: Single project structure chosen. This is a backend service with CLI tools, no frontend required. Discord interaction is API-based. The existing `extracted-rules/` folder is preserved and integrated into the RAG pipeline.

## Phase 0: Outline & Research
1. **Extract unknowns from Technical Context** above:
   - For each NEEDS CLARIFICATION → research task
   - For each dependency → best practices task
   - For each integration → patterns task

2. **Generate and dispatch research agents**:
   ```
   For each unknown in Technical Context:
     Task: "Research {unknown} for {feature context}"
   For each technology choice:
     Task: "Find best practices for {tech} in {domain}"
   ```

3. **Consolidate findings** in `research.md` using format:
   - Decision: [what was chosen]
   - Rationale: [why chosen]
   - Alternatives considered: [what else evaluated]

**Output**: research.md with all NEEDS CLARIFICATION resolved

## Phase 1: Design & Contracts
*Prerequisites: research.md complete*

1. **Extract entities from feature spec** → `data-model.md`:
   - Entity name, fields, relationships
   - Validation rules from requirements
   - State transitions if applicable

2. **Generate API contracts** from functional requirements:
   - For each user action → endpoint
   - Use standard REST/GraphQL patterns
   - Output OpenAPI/GraphQL schema to `/contracts/`

3. **Generate contract tests** from contracts:
   - One test file per endpoint
   - Assert request/response schemas
   - Tests must fail (no implementation yet)

4. **Extract test scenarios** from user stories:
   - Each story → integration test scenario
   - Quickstart test = story validation steps

5. **Update agent file incrementally** (O(1) operation):
   - Run `.specify/scripts/bash/update-agent-context.sh claude`
     **IMPORTANT**: Execute it exactly as specified above. Do not add or remove any arguments.
   - If exists: Add only NEW tech from current plan
   - Preserve manual additions between markers
   - Update recent changes (keep last 3)
   - Keep under 150 lines for token efficiency
   - Output to repository root

**Output**: data-model.md, /contracts/*, failing tests, quickstart.md, agent-specific file

## Phase 2: Task Planning Approach
*This section describes what the /tasks command will do - DO NOT execute during /plan*

**Task Generation Strategy**:
- Load `.specify/templates/tasks-template.md` as base
- Generate tasks from Phase 1 design docs (data-model.md, contracts/, quickstart.md)
- **Contract-driven**:
  - RAG pipeline contract → 6 contract test tasks (one per test case) [P]
  - LLM adapter contract → 6 contract test tasks per provider (18 total) [P]
- **Entity-driven**:
  - 7 entities from data-model.md → 7 model creation tasks [P]
  - Each entity → validation logic + unit tests [P]
- **User story-driven**:
  - 5 acceptance scenarios → 5 integration test tasks
  - Quickstart test scenarios → E2E test tasks
- **Implementation tasks**:
  - RAG service (retrieve + ingest methods)
  - LLM adapters (Claude, ChatGPT, Gemini)
  - Discord bot event handlers
  - PDF ingestion pipeline
  - CLI tools (ingest, test_query, gdpr_delete)
  - Configuration management
  - Logging and observability setup

**Ordering Strategy**:
1. **Setup** (T001-T005): Project structure, dependencies, config templates
2. **Test-First** (T006-T030): Contract tests, model tests (all must FAIL initially)
3. **Core Models** (T031-T037): Implement 7 entities from data-model.md [P where no dependencies]
4. **RAG Pipeline** (T038-T045): Implement retrieval, ingestion, embedding
5. **LLM Adapters** (T046-T051): Claude, ChatGPT, Gemini adapters [P]
6. **Discord Integration** (T052-T060): Bot setup, event handlers, response formatting
7. **PDF Pipeline** (T061-T065): Download, extract, markdown generation
8. **Integration Tests** (T066-T075): Full user journeys, edge cases
9. **Quality & Polish** (T076-T085): Unit tests, performance tests, CI/CD setup, docs

**Parallel Execution Groups**:
- Group 1 [P]: All contract tests (different files)
- Group 2 [P]: Model creation (UserQuery, RuleDocument, RAGContext, etc.)
- Group 3 [P]: LLM adapter implementations (independent providers)
- Group 4 [P]: CLI tools (different commands)

**Estimated Output**: 80-90 numbered, ordered tasks in tasks.md

**Dependencies**:
- Contract tests → Model implementations
- Models → Services
- RAG + LLM adapters → Discord bot integration
- All core implementation → Integration tests
- Integration tests passing → Quality gates & deployment

**IMPORTANT**: This phase is executed by the /tasks command, NOT by /plan

## Phase 3+: Future Implementation
*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution (/tasks command creates tasks.md)  
**Phase 4**: Implementation (execute tasks.md following constitutional principles)  
**Phase 5**: Validation (run tests, execute quickstart.md, performance validation)

## Complexity Tracking
*Fill ONLY if Constitution Check has violations that must be justified*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |


## Progress Tracking
*This checklist is updated during execution flow*

**Phase Status**:
- [x] Phase 0: Research complete (/plan command)
- [x] Phase 1: Design complete (/plan command)
- [x] Phase 2: Task planning complete (/plan command - describe approach only)
- [ ] Phase 3: Tasks generated (/tasks command)
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS
- [x] Post-Design Constitution Check: PASS
- [x] All NEEDS CLARIFICATION resolved
- [x] Complexity deviations documented (none)

**Artifacts Generated**:
- [x] research.md (12 technical decisions documented)
- [x] data-model.md (7 entities with validation rules)
- [x] contracts/rag-pipeline.md (RAG contract with 6 test cases)
- [x] contracts/llm-adapter.md (LLM provider contract with 6 test cases)
- [x] quickstart.md (Developer onboarding guide with 5 test scenarios)
- [x] CLAUDE.md (Agent context file updated)

---
*Based on Constitution v1.1.0 - See `.specify/memory/constitution.md`*
