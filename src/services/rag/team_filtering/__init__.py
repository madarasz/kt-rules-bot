"""Team filtering module for RAG prompt optimization.

This module provides team filtering functionality to reduce token costs
in multi-hop retrieval by identifying and filtering to relevant teams only.

Public API:
    TeamFilter: Main class for filtering teams based on query
    filter_teams_for_query: Convenience function for one-off filtering
"""

from .team_filter import TeamFilter, filter_teams_for_query

__all__ = ["TeamFilter", "filter_teams_for_query"]
