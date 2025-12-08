"""Team filtering for hop evaluation prompt optimization.

Extracts relevant team names from user queries using fuzzy matching
and filters the teams structure to reduce token costs.
"""

from typing import Any

from src.lib.logging import get_logger

from .config import TEAM_ALIASES
from .strategies import (
    AbilityMatchingStrategy,
    AliasMatchingStrategy,
    FuzzyTeamNameStrategy,
    OperativeMatchingStrategy,
)
from .utils import extract_all_items, filter_stop_words, has_common_role_word

logger = get_logger(__name__)


class TeamFilter:
    """Filters teams structure based on query relevance."""

    def __init__(self, teams_structure: dict[str, Any]):
        """Initialize team filter with teams structure.

        Args:
            teams_structure: Full teams structure dictionary
        """
        self.teams_structure = teams_structure
        self._team_names = list(teams_structure.keys())

        # Build keyword caches with pre-filtered stop words
        self._operative_cache: dict[str, dict] = {}
        self._ability_cache: dict[str, dict] = {}
        self._build_keyword_cache()

        # Initialize matching strategies
        self.operative_strategy = OperativeMatchingStrategy(self._operative_cache)
        self.ability_strategy = AbilityMatchingStrategy(self._ability_cache)
        self.alias_strategy = AliasMatchingStrategy(TEAM_ALIASES)
        self.fuzzy_strategy = FuzzyTeamNameStrategy(self._team_names)

        logger.info(
            "team_filter_initialized",
            total_teams=len(self._team_names),
            total_operatives=len(self._operative_cache),
            total_abilities=len(self._ability_cache),
        )

    def _build_keyword_cache(self) -> None:
        """Build mapping from keywords (operatives, rules) to team names.

        Pre-filters stop words during cache building for better performance.
        """
        for team_name, team_data in self.teams_structure.items():
            if not isinstance(team_data, dict):
                continue

            # Extract and cache operatives (with pre-filtered stop words)
            operatives = extract_all_items(team_data.get("Operatives", []))
            for operative in operatives:
                operative_lower = operative.lower()
                operative_words = filter_stop_words(operative_lower)

                # Build cache entry
                if operative_lower not in self._operative_cache:
                    self._operative_cache[operative_lower] = {
                        "teams": [],
                        "words": operative_words,
                        "has_role_words": has_common_role_word(operative_words),
                    }
                self._operative_cache[operative_lower]["teams"].append(team_name)

            # Extract and cache abilities (with pre-filtered stop words)
            abilities = (
                extract_all_items(team_data.get("Faction Rules", []))
                + extract_all_items(team_data.get("Strategy Ploys", []))
                + extract_all_items(team_data.get("Firefight Ploys", []))
                + extract_all_items(team_data.get("Faction Equipment", []))
            )
            for ability in abilities:
                ability_lower = ability.lower()
                ability_words = filter_stop_words(ability_lower)

                # Build cache entry
                if ability_lower not in self._ability_cache:
                    self._ability_cache[ability_lower] = {
                        "teams": [],
                        "words": ability_words,
                    }
                self._ability_cache[ability_lower]["teams"].append(team_name)

    def extract_relevant_teams(self, query: str) -> list[str]:
        """Extract relevant team names from user query using fuzzy matching.

        Args:
            query: User's question

        Returns:
            List of team names (empty if no teams detected)
        """
        query_lower = query.lower()
        query_words = filter_stop_words(query_lower)

        relevant_teams: set[str] = set()

        # Apply all matching strategies
        relevant_teams.update(self.operative_strategy.match(query_lower, query_words))
        relevant_teams.update(self.ability_strategy.match(query_lower, query_words))
        relevant_teams.update(self.alias_strategy.match(query_lower, query_words))
        relevant_teams.update(self.fuzzy_strategy.match(query_lower, query_words))

        result = sorted(relevant_teams)
        logger.info("teams_extracted", query=query, teams_found=len(result), teams=result)
        return result

    def filter_structure(self, relevant_teams: list[str]) -> dict[str, Any]:
        """Filter teams structure to only include relevant teams.

        Args:
            relevant_teams: List of team names to include

        Returns:
            Filtered teams structure (empty dict if no teams detected)
        """
        if not relevant_teams:
            # No teams detected - return empty structure
            return {}

        filtered = {
            team: self.teams_structure[team]
            for team in relevant_teams
            if team in self.teams_structure
        }

        return filtered


def filter_teams_for_query(query: str, teams_structure: dict[str, Any]) -> dict[str, Any]:
    """Convenience function to filter teams structure for a query.

    Args:
        query: User's question
        teams_structure: Full teams structure dictionary

    Returns:
        Filtered teams structure (empty dict if no teams detected)
    """
    team_filter = TeamFilter(teams_structure)
    relevant_teams = team_filter.extract_relevant_teams(query)
    return team_filter.filter_structure(relevant_teams)
