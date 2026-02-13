# Admin Dashboard

Streamlit-based web interface for reviewing bot queries, managing admin status, analyzing performance metrics, and managing RAG test data.

## Purpose

Password-protected dashboard for bot administrators to:
- Review query/response pairs with admin status management
- Analyze feedback trends, costs, and LLM performance
- Mark RAG chunk relevance for training data
- Compare RAG test results across runs
- Export data (CSV/JSON) and manage database cleanup

## Structure

```
src/admin_dashboard/
├── app.py              # Main entry point (Streamlit page config, auth, routing)
├── auth.py             # Password authentication module
├── pages/              # Page renderers (one per dashboard view)
│   ├── query_browser.py    # List/filter queries with cards
│   ├── query_detail.py     # Single query detail with admin controls
│   ├── analytics.py        # Charts and metrics (plotly)
│   ├── rag_test_results.py # RAG test run comparison
│   ├── rag_test_detail.py  # Single RAG test detail view
│   ├── export_tests.py     # Export RAG tests to YAML
│   └── settings.py         # Database info, cleanup, export
├── components/         # Reusable UI components
│   ├── query_card.py       # Query card with preview/status
│   ├── chunk_viewer.py     # RAG chunk display with relevance marking
│   ├── filters.py          # Multi-column filter controls
│   ├── metrics.py          # Metric display widgets
│   ├── server_selector.py  # Discord server dropdown
│   └── deletion.py         # Deletion confirmation dialog
└── utils/              # Shared utilities
    ├── constants.py        # Admin status options, page names
    ├── formatters.py       # Date/time formatting helpers
    ├── icons.py            # Status/validation icon helpers
    └── session.py          # Streamlit session state management
```

## Running the Dashboard

```bash
# Via Streamlit directly
streamlit run src/admin_dashboard/app.py --server.port 8501

# Via CLI wrapper
streamlit run src/cli/admin_dashboard.py --server.port 8501

# Access at http://localhost:8501
```

**Requirements**:
- `ENABLE_ANALYTICS_DB=true` in config/.env
- `ADMIN_DASHBOARD_PASSWORD=<password>` in config/.env

## Pages Overview

### Query Browser (`query_browser.py`)
- Paginated query list with filter controls (date, status, model, server, search)
- Query cards showing preview, feedback counts, timestamps
- Click-through to query detail

### Query Detail (`query_detail.py`)
- Full query/response text display
- Admin status dropdown (pending → approved/flagged/RAG issue/LLM issue)
- Admin notes text area
- Fixed issue checkbox for tracking resolved problems
- RAG chunks table with relevance marking controls

### Analytics (`analytics.py`)
- Overview metrics (total queries, feedback, costs)
- Admin status distribution pie chart
- Latency breakdown by component (retrieval/hop eval/LLM)
- Daily feedback trends (upvotes/downvotes over time)
- Cost analysis with daily breakdown
- LLM model performance comparison table
- Top 50 most downvoted queries
- Quote hallucination detection (validation score < 100%)

### RAG Test Results (`rag_test_results.py`)
- Compare RAG test runs by timestamp
- Pass/fail counts and success rates
- Click-through to test detail

### RAG Test Detail (`rag_test_detail.py`)
- Single test case results across runs
- Retrieved chunks comparison
- Expected vs actual chunk analysis

### Export Tests (`export_tests.py`)
- Export marked queries as RAG test YAML files
- Filter by relevance-marked chunks
- Generate test cases from production data

### Settings (`settings.py`)
- Database path and stats
- Manual cleanup trigger (30-day retention)
- Export to CSV/JSON

## Components

### ChunkViewer (`chunk_viewer.py`)
Displays RAG chunks in table format with:
- Rank, title, hop number, scores (final/vector/BM25/RRF)
- Inline relevance buttons (Y/N/?) for marking training data
- Session state persistence for unsaved changes

### QueryFilters (`filters.py`)
Multi-column filter bar with:
- Date range (start/end)
- Admin status dropdown
- LLM model dropdown
- Discord server dropdown
- Text search input
- Feedback toggles (has upvotes/downvotes)

### QueryCard (`query_card.py`)
Compact query preview showing:
- Timestamp and query text preview
- Admin status badge
- Feedback counts (upvotes/downvotes)
- View detail button

## Admin Status Workflow

```
pending (default)
    ├→ approved     # Response verified correct
    ├→ flagged      # Response needs attention
    ├→ RAG issue    # Wrong/missing chunks retrieved
    └→ LLM issue    # Correct chunks, wrong answer
```

Status values defined in `utils/constants.py`:
```python
ADMIN_STATUS_OPTIONS = ["pending", "approved", "flagged", "RAG issue", "LLM issue"]
```

## Integration

**Database**: `src/lib/database.py` (`AnalyticsDatabase` class)
- SQLite storage with 30-day retention
- Stores queries, responses, feedback, chunks, admin status

**Config**: `src/lib/config.py`
- `ADMIN_DASHBOARD_PASSWORD` - login password
- `ENABLE_ANALYTICS_DB` - must be true

**Data Flow**:
```
Discord bot → analytics_recorder → AnalyticsDatabase → Admin Dashboard
```

## Dependencies

- **streamlit** - Web framework
- **pandas** - Data manipulation
- **plotly** - Interactive charts
- **src/lib/database** - Data access layer

## Development Guidelines

### Adding New Pages
1. Create `pages/my_page.py` with `def render(db: AnalyticsDatabase)` function
2. Add page name to `utils/constants.py` PAGE_NAMES dict
3. Import and add routing in `app.py` (render_sidebar, route_to_page)

### Adding New Components
1. Create `components/my_component.py` with class or function
2. Use Streamlit session state for persistent UI state
3. Import from page modules as needed

### Session State
Use `utils/session.py` helpers for:
- Navigation (`navigate_to_page`, `get_current_page`)
- Query selection (`set_selected_query`)
- Chunk relevance tracking (`init_chunk_relevance_state`, etc.)

### Best Practices
- Keep pages focused on single views
- Extract reusable UI into components
- Use session state for cross-page navigation
- Format data with utils/formatters.py helpers
