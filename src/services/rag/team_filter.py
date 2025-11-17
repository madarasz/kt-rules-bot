"""Team filtering for hop evaluation prompt optimization.

Extracts relevant team names from user queries using fuzzy matching
and filters the teams structure to reduce token costs.
"""

from typing import Any

from rapidfuzz import fuzz, process

from src.lib.logging import get_logger

logger = get_logger(__name__)

# Fuzzy matching threshold (0-100)
TEAM_MATCH_THRESHOLD = 80

# Stop words to filter out (common English words with low semantic value)
# These appear in ability/ploy names but cause false positives when matching
STOP_WORDS = {
    # Articles
    "the", "a", "an", "this", "these", "those",
    # Prepositions
    "from", "with", "for", "before", "after", "into", "onto", "upon", "over", "under",
    "through", "across", "along", "behind", "beyond", "near", "beside", "of", "to", "in", "on", "at",
    # Conjunctions
    "and", "or", "but", "that", "thus", "then", "than", "as", "if", "when", "where",
    # Pronouns
    "his", "her", "its", "their", "your", "my", "our", "it", "he", "she", "they", "we",
    # Common verbs (auxiliary/modal and 'be' forms)
    "would", "could", "should", "will", "can", "may", "might", "must", "shall",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did",
    # Quantifiers
    "all", "any", "some", "few", "many", "much", "more", "most", "less", "least",
    # Other common words
    "not", "no", "yes", "also", "just", "only", "very", "too", "so", "such",
    # Game-specific common words (appear in many ability/operative names)
    # "blood", "field", "battle", "death", "kill", "shot", "fire", "dark", "light",
}

# Common abbreviations and alternative names
TEAM_ALIASES = {
    "space marines": ["Angels Of Death", "Deathwatch", "Phobos Strike Team", "Scout Squad",
                 "Legionaries", "Plague Marines", "Nemesis Claw"],
    "astartes": ["Angels Of Death", "Deathwatch", "Phobos Strike Team", "Scout Squad",
                 "Legionaries", "Plague Marines", "Nemesis Claw"],
    "chaos": ["Blooded", "Chaos Cult", "Legionaries", "Plague Marines", "Warpcoven",
              "Nemesis Claw", "Fellgor Ravagers", "Goremongers"],
    "orks": ["Kommandos", "Wrecka Krew"],
    "tau": ["Pathfinders", "Vespid Stingwings", "Farstalker Kinband"],
    "kroot": ["Farstalker Kinband"],
    "kroots": ["Farstalker Kinband"],
    "eldar": ["Blades Of Khaine", "Corsair Voidscarred", "Void Dancer Troupe", "Hand Of The Archon", "Mandrakes"],
    "aeldari": ["Blades Of Khaine", "Corsair Voidscarred", "Void Dancer Troupe", "Hand Of The Archon", "Mandrakes"],
    "guard": ["Death Korps", "Kasrkin", "Tempestus Aquilons", "Imperial Navy Breachers"],
    "imperial guard": ["Death Korps", "Kasrkin", "Tempestus Aquilons", "Imperial Navy Breachers"],
    "necrons": ["Hierotek Circle", "Canoptek Circle"],
    "drukhari": ["Hand Of The Archon", "Mandrakes"],
    "dark eldar": ["Hand Of The Archon", "Mandrakes"],
    "genestealer": ["Wyrmblade", "Brood Brothers"],
    "tyranids": ["Raveners"],
    "squats": ["Hearthkyn Salvagers", "Hernkyn Yaegirs"],
    "votann": ["Hearthkyn Salvagers", "Hernkyn Yaegirs"],
    "mechanicus": ["Hunter Clade", "Battleclade"],
    "admech": ["Hunter Clade", "Battleclade"],
}


class TeamFilter:
    """Filters teams structure based on query relevance."""

    def __init__(self, teams_structure: dict[str, Any]):
        """Initialize team filter with teams structure.

        Args:
            teams_structure: Full teams structure dictionary
        """
        self.teams_structure = teams_structure
        self._team_names = list(teams_structure.keys())

        # Build keyword caches: separate operatives from abilities/ploys
        self._operative_to_teams: dict[str, list[str]] = {}  # Operative names (single-word match)
        self._ability_to_teams: dict[str, list[str]] = {}  # Abilities/ploys (multi-word match)
        self._build_keyword_cache()

        logger.info(
            "team_filter_initialized",
            total_teams=len(self._team_names),
            total_operatives=len(self._operative_to_teams),
            total_abilities=len(self._ability_to_teams),
        )

    def _build_keyword_cache(self) -> None:
        """Build mapping from keywords (operatives, rules) to team names."""
        for team_name, team_data in self.teams_structure.items():
            if not isinstance(team_data, dict):
                continue

            # Add operatives (use single-word matching)
            for operative in team_data.get("Operatives", []):
                operative_lower = operative.lower()
                if operative_lower not in self._operative_to_teams:
                    self._operative_to_teams[operative_lower] = []
                self._operative_to_teams[operative_lower].append(team_name)

            # Add faction rules, ploys (use multi-word matching)
            abilities = (
                team_data.get("Faction Rules", []) +
                team_data.get("Strategy Ploys", []) +
                team_data.get("Firefight Ploys", []) +
                team_data.get("Faction Equipment", [])
            )
            for ability in abilities:
                ability_lower = ability.lower()
                if ability_lower not in self._ability_to_teams:
                    self._ability_to_teams[ability_lower] = []
                self._ability_to_teams[ability_lower].append(team_name)

    def extract_relevant_teams(self, query: str) -> list[str]:
        """Extract relevant team names from user query using fuzzy matching.

        Args:
            query: User's question

        Returns:
            List of team names (empty if no teams detected)
        """
        query_lower = query.lower()
        relevant_teams: set[str] = set()

        # Filter query words to remove stop words (for alias matching)
        query_words = [w for w in query_lower.split() if w not in STOP_WORDS]

        # 1. Check operative names (prefer multi-word matches, fall back to single-word)
        for operative, teams in self._operative_to_teams.items():
            if len(operative) < 4:
                continue

            # Skip stop words to avoid matches like "FIELD MEDIC" matching "battlefield"
            operative_words = [w for w in operative.split() if w not in STOP_WORDS]

            # Count how many operative words match
            matched_words = [w for w in operative_words if len(w) >= 4 and w in query_lower]
            match_count = len(matched_words)

            # Matching criteria:
            # - Single-word operatives: require 1 word match
            # - 2-word operatives: require 1+ word match
            # - 3+ word operatives: require 1 distinctive word (6+ chars) OR 2+ regular words
            has_distinctive_match = any(len(w) >= 6 for w in matched_words)

            if len(operative_words) >= 3:
                required_matches = 1 if has_distinctive_match else 2
            else:
                required_matches = 1

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

        # 2. Check abilities/ploys (multi-word matching, more strict)
        for ability, teams in self._ability_to_teams.items():
            if len(ability) < 4:
                continue

            ability_words = [w for w in ability.split() if w not in STOP_WORDS]
            ability_words_count = len(ability_words)

            # Skip if all words are stop words
            if ability_words_count == 0:
                continue

            # Count how many ability words appear in query
            matched_words = [w for w in ability_words if w in query_lower]
            match_count = len(matched_words)

            # Matching criteria:
            # - Single-word abilities: require exact match
            # - 2-word abilities: require 2/2 words (exact phrase)
            # - 3+ word abilities: require 2+ words to match
            required_matches = 1 if ability_words_count == 1 else min(2, ability_words_count)

            if match_count >= required_matches:
                relevant_teams.update(teams)
                logger.debug(
                    "ability_match",
                    ability=ability,
                    matched_words=matched_words,
                    match_count=match_count,
                    required=required_matches,
                    teams=teams,
                )

        # 3. Check for team aliases (bidirectional fuzzy match)
        for alias, teams in TEAM_ALIASES.items():
            # Check if alias is in query OR fuzzy match on words
            if alias in query_lower:
                relevant_teams.update(teams)
            else:
                # Try fuzzy matching alias words against filtered query words
                alias_words = alias.split()
                for alias_word in alias_words:
                    if len(alias_word) >= 4:
                        for query_word in query_words:
                            if len(query_word) >= 4:
                                similarity = fuzz.ratio(alias_word, query_word)
                                if similarity >= TEAM_MATCH_THRESHOLD:
                                    relevant_teams.update(teams)
                                    break

        # 4. Fuzzy match against team names
        # Use filtered query words
        for word in query_words:
            if len(word) < 4:  # Skip short words
                continue

            # Try fuzzy matching against team names
            match = process.extractOne(
                word,
                self._team_names,
                scorer=fuzz.ratio,
                score_cutoff=TEAM_MATCH_THRESHOLD,
            )
            if match:
                team_name, score, _ = match
                relevant_teams.add(team_name)
                logger.debug(
                    "team_fuzzy_match",
                    word=word,
                    team=team_name,
                    score=score,
                )

        result = sorted(relevant_teams)
        logger.info(
            "teams_extracted",
            query=query,
            teams_found=len(result),
            teams=result,
        )
        return result

    def filter_structure(self, relevant_teams: list[str]) -> dict[str, Any]:
        """Filter teams structure to only include relevant teams.

        Args:
            relevant_teams: List of team names to include

        Returns:
            Filtered teams structure (or full structure if empty list)
        """
        if not relevant_teams:
            # No teams detected - return full structure
            return self.teams_structure

        filtered = {
            team: self.teams_structure[team]
            for team in relevant_teams
            if team in self.teams_structure
        }

        return filtered


def filter_teams_for_query(
    query: str,
    teams_structure: dict[str, Any],
) -> dict[str, Any]:
    """Convenience function to filter teams structure for a query.

    Args:
        query: User's question
        teams_structure: Full teams structure dictionary

    Returns:
        Filtered teams structure (or full structure if no teams detected)
    """
    team_filter = TeamFilter(teams_structure)
    relevant_teams = team_filter.extract_relevant_teams(query)
    return team_filter.filter_structure(relevant_teams)
