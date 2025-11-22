"""Constants for the admin dashboard."""

ADMIN_STATUS_OPTIONS = [
    "pending",
    "approved",
    "reviewed",
    "issues",
    "flagged",
    "RAG issue",
    "LLM issue",
]

ADMIN_STATUS_COLORS = {
    "pending": "🟡",
    "approved": "🟢",
    "reviewed": "🔵",
    "issues": "🟠",
    "flagged": "🔴",
    "RAG issue": "🟣",
    "LLM issue": "🟤",
}

PAGE_NAMES = {
    "QUERY_BROWSER": "📋 Query Browser",
    "QUERY_DETAIL": "🔍 Query Detail",
    "ANALYTICS": "📊 Analytics",
    "RAG_TEST_RESULTS": "📊 RAG Test Results",
    "RAG_TEST_DETAIL": "🔬 RAG Test Detail",
    "EXPORT_TESTS": "🧪 Export Tests",
    "SETTINGS": "⚙️ Settings",
}
