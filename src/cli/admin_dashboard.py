"""Admin dashboard for query analytics and review.

Streamlit web UI for reviewing queries, responses, feedback, and RAG chunks.
Password-protected access.

Usage:
    streamlit run src/cli/admin_dashboard.py --server.port 8501

Note: This is a thin wrapper around the refactored dashboard app.
      The actual implementation is in src/admin_dashboard/
"""
# ruff: noqa: E402

import sys
from pathlib import Path

# Add project root to Python path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.admin_dashboard.app import main

if __name__ == "__main__":
    main()
