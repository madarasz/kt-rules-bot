"""Matching strategies for team filtering.

This module implements the Strategy pattern for different team matching approaches:
- Operative matching: Match character/unit names
- Ability matching: Match faction rules, ploys, equipment
- Alias matching: Match faction abbreviations and alternative names
- Fuzzy team name matching: Direct fuzzy matching against team names
"""

from abc import ABC, abstractmethod

from rapidfuzz import fuzz, process

from src.lib.logging import get_logger

from .config import (
    COMMON_ROLE_WORDS,
    DISTINCTIVE_WORD_LENGTH,
    MIN_WORD_LENGTH,
    TEAM_MATCH_THRESHOLD,
)
from .utils import words_adjacent_in_text

logger = get_logger(__name__)


class MatchingStrategy(ABC):
    """Abstract base class for team matching strategies."""

    @abstractmethod
    def match(self, query_lower: str, query_words: list[str]) -> set[str]:
        """Match teams based on query.

        Args:
            query_lower: Lowercased query string
            query_words: Pre-filtered query words (stop words removed)

        Returns:
            Set of matched team names
        """
        pass


class OperativeMatchingStrategy(MatchingStrategy):
    """Match operative names (character units) from teams to query words.

    Uses multi-word matching with special handling for common role words
    to reduce false positives.
    """

    def __init__(self, operative_cache: dict[str, dict]):
        """Initialize with pre-built operative cache.

        Args:
            operative_cache: Dict mapping operative names to:
                {
                    'teams': [team_name, ...],
                    'words': [word1, word2, ...],  # Stop words removed
                    'has_role_words': bool
                }
        """
        self.operative_cache = operative_cache

    def match(self, query_lower: str, _: list[str]) -> set[str]:
        """Match operatives in query."""
        relevant_teams: set[str] = set()

        for operative, cache_entry in self.operative_cache.items():
            if len(operative) < MIN_WORD_LENGTH:
                continue

            operative_words = cache_entry["words"]
            has_common_words = cache_entry["has_role_words"]
            teams = cache_entry["teams"]

            # For operatives ≤2 words with common role words, require phrase adjacency
            if len(operative_words) <= 2 and has_common_words:
                if words_adjacent_in_text(operative_words, query_lower):
                    relevant_teams.update(teams)
                    logger.debug(
                        "operative_phrase_match",
                        operative=operative,
                        words=operative_words,
                        teams=teams,
                    )
                continue

            # Count how many operative words match
            matched_words = [w for w in operative_words if len(w) >= MIN_WORD_LENGTH and w in query_lower]
            match_count = len(matched_words)

            # For 3+ word operatives with common role words, require at least one distinctive word
            if len(operative_words) >= 3 and has_common_words:
                distinctive_matches = [
                    w for w in matched_words
                    if len(w) >= DISTINCTIVE_WORD_LENGTH and w not in COMMON_ROLE_WORDS
                ]
                if not distinctive_matches:
                    # No distinctive word matched, skip this operative
                    continue

            # Determine required matches based on operative length
            required_matches = self._calculate_required_matches(operative_words, matched_words)

            if match_count >= required_matches:
                relevant_teams.update(teams)
                logger.debug(
                    "operative_match",
                    operative=operative,
                    matched_words=matched_words,
                    match_count=match_count,
                    required=required_matches,
                    teams=teams,
                )

        return relevant_teams

    def _calculate_required_matches(self, operative_words: list[str], matched_words: list[str]) -> int:
        """Calculate required matches for operative matching.

        Args:
            operative_words: Words in operative name (stop words filtered)
            matched_words: Words that matched in query

        Returns:
            Required number of matches
        """
        # Single-word operatives: require 1 word match
        # 2-word operatives: require 1+ word match
        # 3+ word operatives: require 1 distinctive word (6+ chars, not role word) OR 2+ regular words
        has_distinctive_match = any(
            len(w) >= DISTINCTIVE_WORD_LENGTH and w not in COMMON_ROLE_WORDS for w in matched_words
        )

        if len(operative_words) >= 3:
            return 1 if has_distinctive_match else 2
        else:
            return 1


class AbilityMatchingStrategy(MatchingStrategy):
    """Match abilities/ploys in query (multi-word matching, stricter than operatives).

    Requires more words to match to prevent false positives from generic ability names.
    """

    def __init__(self, ability_cache: dict[str, dict]):
        """Initialize with pre-built ability cache.

        Args:
            ability_cache: Dict mapping ability names to:
                {
                    'teams': [team_name, ...],
                    'words': [word1, word2, ...]  # Stop words removed
                }
        """
        self.ability_cache = ability_cache

    def match(self, query_lower: str, _: list[str]) -> set[str]:
        """Match abilities in query."""
        relevant_teams: set[str] = set()

        for ability, cache_entry in self.ability_cache.items():
            if len(ability) < MIN_WORD_LENGTH:
                continue

            ability_words = cache_entry["words"]
            ability_words_count = len(ability_words)

            # Skip if all words are stop words
            if ability_words_count == 0:
                continue

            # Count how many ability words appear in query
            matched_words = [w for w in ability_words if w in query_lower]
            match_count = len(matched_words)

            # Determine required matches
            required_matches = self._calculate_required_matches(ability_words_count)

            if match_count >= required_matches:
                teams = cache_entry["teams"]
                relevant_teams.update(teams)
                logger.debug(
                    "ability_match",
                    ability=ability,
                    matched_words=matched_words,
                    match_count=match_count,
                    required=required_matches,
                    teams=teams,
                )

        return relevant_teams

    def _calculate_required_matches(self, ability_words_count: int) -> int:
        """Calculate required matches for ability matching.

        Args:
            ability_words_count: Number of words in ability

        Returns:
            Required number of matches
        """
        # Single-word abilities: require exact match
        # 2-word abilities: require 2/2 words (exact phrase)
        # 3+ word abilities: require 2+ words to match
        return 1 if ability_words_count == 1 else min(2, ability_words_count)


class AliasMatchingStrategy(MatchingStrategy):
    """Match team aliases in query (bidirectional fuzzy match).

    Handles faction abbreviations and alternative names like "orks", "chaos", "guard".
    """

    def __init__(self, team_aliases: dict[str, list[str]]):
        """Initialize with team aliases configuration.

        Args:
            team_aliases: Dict mapping aliases to team name lists
        """
        self.team_aliases = team_aliases

    def match(self, query_lower: str, query_words: list[str]) -> set[str]:
        """Match aliases in query."""
        relevant_teams: set[str] = set()

        for alias, teams in self.team_aliases.items():
            # Check if alias is in query (exact substring match)
            if alias in query_lower:
                relevant_teams.update(teams)
                continue

            # Try fuzzy matching alias words against filtered query words
            if self._fuzzy_match_alias(alias, query_words):
                relevant_teams.update(teams)

        return relevant_teams

    def _fuzzy_match_alias(self, alias: str, query_words: list[str]) -> bool:
        """Fuzzy match alias against query words.

        Args:
            alias: Alias string
            query_words: Query words with stop words filtered

        Returns:
            True if fuzzy match found
        """
        alias_words = alias.split()
        for alias_word in alias_words:
            if len(alias_word) >= MIN_WORD_LENGTH:
                for query_word in query_words:
                    if len(query_word) >= MIN_WORD_LENGTH:
                        similarity = fuzz.ratio(alias_word, query_word)
                        if similarity >= TEAM_MATCH_THRESHOLD:
                            return True
        return False


class FuzzyTeamNameStrategy(MatchingStrategy):
    """Fuzzy match against team names directly.

    Handles typos and variations in team names using Levenshtein distance.
    """

    def __init__(self, team_names: list[str]):
        """Initialize with list of team names.

        Args:
            team_names: List of all team names
        """
        self.team_names = team_names

    def match(self, _: str, query_words: list[str]) -> set[str]:
        """Fuzzy match team names in query."""
        relevant_teams: set[str] = set()

        for word in query_words:
            if len(word) < MIN_WORD_LENGTH:  # Skip short words
                continue

            # Try fuzzy matching against team names
            match = process.extractOne(
                word, self.team_names, scorer=fuzz.ratio, score_cutoff=TEAM_MATCH_THRESHOLD
            )
            if match:
                team_name, score, _ = match
                relevant_teams.add(team_name)
                logger.debug("team_fuzzy_match", word=word, team=team_name, score=score)

        return relevant_teams
