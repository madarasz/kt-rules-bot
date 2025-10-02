# Feature Specification: Kill Team Rules Discord Bot

**Feature Branch**: `001-we-are-building`
**Created**: 2025-10-02
**Status**: Draft
**Input**: User description: "We are building a Discord bot which helps users understand the rules of the boardgame Kill Team (3rd edition). It answers rule related questions and explains with rule citations when @ mentioned in the Discord server. The rules are collected in markdown files in @extracted-rules folder which should be ingested into a RAG solution with an LLM AI agent interacting with the users. The game receives frequent updates, so we should have automated pipelines to download rules updates as PDF files and add or edit our markdown rules and reingest them into RAG."

## Clarifications

### Session 2025-10-02
- Q: What is the primary purpose for logging user queries and bot responses (FR-012)? → A: All of the above (debugging, analytics, and compliance)
- Q: How should the bot validate response relevance before sending to users (FR-013)? → A: Combined validation (both LLM confidence AND RAG retrieval scores must meet thresholds)
- Q: What are acceptable minimum targets for RAG retrieval precision/recall (NFR-002)? → A: High precision (Precision ≥90%, Recall ≥70% - prioritize accuracy over completeness)
- Q: When base rules and FAQ updates contradict each other, how should the bot resolve the conflict? → A: FAQ and recent rules updates always take priority
- Q: How should concurrent user conversations be isolated to prevent cross-talk (FR-011)? → A: Channel + User isolation (combination of channel ID and user ID for context tracking)

## User Scenarios & Testing

### Primary User Story

A Kill Team player is participating in a Discord server dedicated to the game. During gameplay or discussion, they have a question about a specific rule (e.g., "Can I shoot through a barricade?"). They mention the bot in a message with their question. The bot responds with an accurate answer, citing the specific rule sections from the official Kill Team 3rd edition rulebook that support the answer.

### Acceptance Scenarios

1. **Given** a user is in a Discord server with the bot installed, **When** they @ mention the bot with a rules question like "What actions can I take during the movement phase?", **Then** the bot responds with an accurate answer including citations to relevant rule sections (e.g., "rules-1-phases.md", "rules-2-actions.md").

2. **Given** the Kill Team rulebook receives an official update (FAQ, errata, or new edition content), **When** the automated update pipeline runs, **Then** the system downloads the new PDF, extracts/updates the relevant markdown files, and re-ingests the content into the RAG system without manual intervention.

3. **Given** a user asks an ambiguous question, **When** the bot processes the query, **Then** the bot asks clarifying questions or provides multiple relevant answers with context for the user to choose from.

4. **Given** a user asks about a rule that doesn't exist or is outside Kill Team 3rd edition scope, **When** the bot searches for relevant information, **Then** the bot responds that it cannot find relevant rules and suggests alternative phrasings or confirms the scope limitation.

5. **Given** multiple users ask questions simultaneously, **When** the bot receives concurrent @ mentions, **Then** each user receives an accurate, contextual response without confusion or cross-talk between conversations.

### Edge Cases

- What happens when the bot is mentioned without a clear question (e.g., just "@bot hello")?
- What happens when a PDF update fails to download or parse correctly?
- How does the bot respond to questions about rules from previous editions (not 3rd edition)?
- What happens when the RAG system retrieves conflicting information from different markdown files?
- How does the system handle rate limiting from Discord's API during high-traffic periods?
- What happens when the extracted-rules folder contains malformed or corrupted markdown files?

## Requirements

### Functional Requirements

- **FR-001**: Bot MUST respond to @ mentions in Discord servers where it is installed.
- **FR-002**: Bot MUST parse user questions from Discord messages and extract the rules query.
- **FR-003**: Bot MUST use RAG to retrieve relevant rule sections from ingested markdown files.
- **FR-004**: Bot MUST provide answers with citations to source markdown files and specific sections.
- **FR-005**: Bot MUST ingest all markdown files from the extracted-rules folder into the RAG system.
- **FR-006**: Bot MUST support questions about Kill Team 3rd edition rules (phases, actions, key principles, killzones, tactical operations, weapons, FAQ).
- **FR-007**: System MUST provide an automated pipeline to download official Kill Team rule updates as PDF files on a on-demand trigger via CLI.
- **FR-008**: System MUST extract text from downloaded PDFs and create or update markdown files in extracted-rules folder.
- **FR-009**: System MUST automatically re-ingest updated markdown content into RAG when rule updates are processed.
- **FR-010**: Bot MUST distinguish between questions it can answer and questions outside its knowledge scope.
- **FR-011**: Bot MUST handle concurrent requests from multiple users without response mixing or data corruption by tracking conversation context using a combination of channel ID and user ID (allowing same user to have different conversations in different channels).
- **FR-012**: System MUST log all user queries and bot responses for debugging (troubleshooting errors and performance), analytics (tracking common questions, bot accuracy, user satisfaction metrics), and compliance (legal/regulatory record-keeping for moderation or dispute resolution).
- **FR-013**: Bot MUST validate that responses are relevant to the user's question before sending using combined validation: both LLM confidence score (minimum threshold) AND RAG retrieval similarity score (minimum threshold) must be met. If validation fails, bot responds that it cannot confidently answer and suggests rephrasing.
- **FR-014**: System MUST track which version of rules is currently active (to support answer citations from correct edition/FAQ version).
- **FR-015**: Bot MUST handle Discord message length limits by splitting long responses into multiple messages or using embeds.
- **FR-016**: Bot MUST detect rule contradictions between different source documents (base rules vs FAQ/errata). When detected, bot MUST NOT provide an answer, log the conflict with source citations, and inform the user that manual clarification is required.

### Non-Functional Requirements

- **NFR-001**: Bot response latency MUST be <30 seconds from @ mention to first response.
- **NFR-002**: RAG retrieval precision MUST be ≥90% and recall MUST be ≥70% to ensure accurate rule citations (prioritizing answer accuracy over completeness).
- **NFR-003**: System MUST support 5 concurrent user capacity simultaneous Discord interactions.
- **NFR-004**: System MUST be resilient to PDF format changes in official rule publications, and give an alert/output if there were ambiguities or processing issues.
- **NFR-005**: All user data and Discord interactions MUST comply with Discord's Terms of Service and API rate limits.
- **NFR-006**: System MUST comply with GDPR for user message storage and logging, data retention period is 1 week.

### Key Entities

- **User Query**: A question from a Discord user about Kill Team rules, containing the message text, user ID, channel ID, timestamp, and conversation context (tracked by channel ID + user ID combination to isolate concurrent conversations).

- **Rule Document**: A markdown file in extracted-rules folder representing a section of Kill Team rules, containing the document name, content, version/timestamp, and source PDF reference.

- **RAG Context**: Retrieved rule sections relevant to a user query, containing document chunks, relevance scores, source citations, and metadata for answer generation.

- **PDF Update**: An official Kill Team rules document (core rules, FAQ, errata), containing the PDF file, publication date, version identifier, and change summary.

- **Bot Response**: An answer to a user query, containing the answer text, rule citations, confidence level, and conversation thread ID.

- **Ingestion Job**: An automated process that converts PDFs to markdown and updates the RAG system, containing job ID, status, processed files list, errors/warnings, and completion timestamp.

## Dependencies and Assumptions

**Dependencies**:
- Discord Bot API access and authentication token
- Existing extracted-rules folder with 12 markdown files (as shown in user's repository)
- Official Kill Team PDF sources via API: https://www.warhammer-community.com/api/search/downloads/
- LLM provider API: Claude, Gemini, ChatGpt

**Assumptions**:
- Kill Team 3rd edition is the current focus; previous editions are out of scope
- Rule updates are published as PDFs by the game publisher (Games Workshop)
- Markdown format in extracted-rules folder follows a consistent structure
- Discord server administrators will install and configure the bot with appropriate permissions
- Users will @ mention the bot to trigger interactions (not listening to all messages)

## Success Criteria

- Bot successfully responds to @ mentions with rule citations in Discord
- Automated pipeline downloads and processes PDF updates without manual intervention
- RAG system provides accurate answers with source traceability
- Response latency meets user expectations for interactive chat
- System maintains compliance with Discord ToS and GDPR requirements

---

## Review & Acceptance Checklist

### Content Quality
- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

### Requirement Completeness
- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

---

## Execution Status

- [x] User description parsed
- [x] Key concepts extracted
- [x] Ambiguities marked
- [x] User scenarios defined
- [x] Requirements generated
- [x] Entities identified
- [x] Review checklist passed

---
