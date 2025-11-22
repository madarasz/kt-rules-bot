"""Tests for team filtering matching strategies."""

import pytest

from src.services.rag.team_filtering.config import TEAM_ALIASES
from src.services.rag.team_filtering.strategies import (
    AbilityMatchingStrategy,
    AliasMatchingStrategy,
    FuzzyTeamNameStrategy,
    OperativeMatchingStrategy,
)


class TestOperativeMatchingStrategy:
    """Tests for operative matching strategy."""

    @pytest.fixture
    def operative_cache(self):
        """Sample operative cache for testing."""
        return {
            "kommando": {
                "teams": ["Kommandos"],
                "words": ["kommando"],
                "has_role_words": False,
            },
            "ork boy fighter": {
                "teams": ["Kommandos"],
                "words": ["ork", "boy", "fighter"],
                "has_role_words": True,  # "fighter" is a role word
            },
            "scout gunner": {
                "teams": ["Phobos Strike Team"],
                "words": ["scout", "gunner"],
                "has_role_words": True,  # "gunner" is a role word
            },
            "assault intercessor warrior": {
                "teams": ["Angels Of Death"],
                "words": ["assault", "intercessor", "warrior"],
                "has_role_words": True,  # "warrior" is a role word
            },
            "pathfinder warrior": {
                "teams": ["Pathfinders"],
                "words": ["pathfinder", "warrior"],
                "has_role_words": True,
            },
        }

    @pytest.fixture
    def strategy(self, operative_cache):
        """Create strategy instance."""
        return OperativeMatchingStrategy(operative_cache)

    def test_single_word_operative_exact_match(self, strategy):
        """Test single-word operative with exact match."""
        result = strategy.match("kommando abilities", ["kommando", "abilities"])
        assert "Kommandos" in result

    def test_single_word_operative_no_match(self, strategy):
        """Test single-word operative with no match."""
        result = strategy.match("pathfinder abilities", ["pathfinder", "abilities"])
        assert "Kommandos" not in result

    def test_two_word_operative_with_role_word_adjacent(self, strategy):
        """Test 2-word operative with role word requires adjacency."""
        # Adjacent - should match
        result = strategy.match("scout gunner abilities", ["scout", "gunner", "abilities"])
        assert "Phobos Strike Team" in result

    def test_two_word_operative_with_role_word_not_adjacent(self, strategy):
        """Test 2-word operative with role word not adjacent - no match."""
        # Not adjacent - should NOT match
        result = strategy.match("gunner can scout ahead", ["gunner", "scout", "ahead"])
        assert "Phobos Strike Team" not in result

    def test_multi_word_operative_with_distinctive_word(self, strategy):
        """Test 3+ word operative with distinctive word."""
        # "assault" is 7 chars (distinctive)
        result = strategy.match("assault abilities", ["assault", "abilities"])
        assert "Angels Of Death" in result

    def test_multi_word_operative_without_distinctive_word(self, strategy):
        """Test 3+ word operative needs distinctive word or 2+ matches."""
        # Only "warrior" matches (6 chars but is role word, not distinctive)
        result = strategy.match("warrior abilities", ["warrior", "abilities"])
        assert "Angels Of Death" not in result

    def test_multi_word_operative_with_two_regular_matches(self, strategy):
        """Test 3+ word operative with 2 regular word matches."""
        # "assault" and "warrior" both match
        result = strategy.match("assault warrior", ["assault", "warrior"])
        assert "Angels Of Death" in result


class TestAbilityMatchingStrategy:
    """Tests for ability matching strategy."""

    @pytest.fixture
    def ability_cache(self):
        """Sample ability cache for testing."""
        return {
            "astartes": {
                "teams": ["Angels Of Death", "Deathwatch"],
                "words": ["astartes"],
            },
            "ere go": {  # "we" is stop word
                "teams": ["Kommandos"],
                "words": ["ere", "go"],
            },
            "combat doctrine": {
                "teams": ["Angels Of Death"],
                "words": ["combat", "doctrine"],
            },
            "adjust doctrine ploy": {
                "teams": ["Angels Of Death"],
                "words": ["adjust", "doctrine", "ploy"],
            },
        }

    @pytest.fixture
    def strategy(self, ability_cache):
        """Create strategy instance."""
        return AbilityMatchingStrategy(ability_cache)

    def test_single_word_ability_exact_match(self, strategy):
        """Test single-word ability requires exact match."""
        result = strategy.match("astartes abilities", ["astartes", "abilities"])
        assert "Angels Of Death" in result
        assert "Deathwatch" in result

    def test_single_word_ability_no_match(self, strategy):
        """Test single-word ability with no match."""
        result = strategy.match("space marine abilities", ["space", "marine", "abilities"])
        assert "Angels Of Death" not in result

    def test_two_word_ability_both_words_match(self, strategy):
        """Test 2-word ability requires both words."""
        result = strategy.match("ere we go ability", ["ere", "go", "ability"])
        assert "Kommandos" in result

    def test_two_word_ability_one_word_match(self, strategy):
        """Test 2-word ability with only one word - no match."""
        result = strategy.match("where does ere work", ["ere", "work"])
        assert "Kommandos" not in result

    def test_multi_word_ability_two_matches(self, strategy):
        """Test 3+ word ability requires 2+ words."""
        # "adjust" and "doctrine" match
        result = strategy.match("adjust doctrine", ["adjust", "doctrine"])
        assert "Angels Of Death" in result

    def test_multi_word_ability_one_match(self, strategy):
        """Test 3+ word ability with only one word - no match."""
        result = strategy.match("doctrine abilities", ["doctrine", "abilities"])
        # Only "doctrine" matches, need 2+ for 3-word ability
        assert "Angels Of Death" not in result


class TestAliasMatchingStrategy:
    """Tests for alias matching strategy."""

    @pytest.fixture
    def strategy(self):
        """Create strategy instance."""
        return AliasMatchingStrategy(TEAM_ALIASES)

    def test_exact_alias_match(self, strategy):
        """Test exact alias substring match."""
        result = strategy.match("what can orks do", ["orks"])
        assert "Kommandos" in result
        assert "Wrecka Krew" in result

    def test_fuzzy_alias_match(self, strategy):
        """Test fuzzy alias matching (typo tolerance)."""
        # "chaos" misspelled as "choas" should fuzzy match (83% similarity)
        result = strategy.match("what can choas do", ["choas"])
        # Should match some chaos teams (8 total)
        assert len(result) > 0

    def test_multi_word_alias(self, strategy):
        """Test multi-word alias matching."""
        result = strategy.match("space marines abilities", ["space", "marines", "abilities"])
        assert "Angels Of Death" in result
        assert "Deathwatch" in result

    def test_no_alias_match(self, strategy):
        """Test query with no alias matches."""
        result = strategy.match("generic question", ["generic", "question"])
        assert len(result) == 0


class TestFuzzyTeamNameStrategy:
    """Tests for fuzzy team name matching strategy."""

    @pytest.fixture
    def team_names(self):
        """Sample team names."""
        return [
            "Kommandos",
            "Pathfinders",
            "Death Korps",
            "Deathwatch",
            "Kasrkin",
        ]

    @pytest.fixture
    def strategy(self, team_names):
        """Create strategy instance."""
        return FuzzyTeamNameStrategy(team_names)

    def test_exact_team_name_match(self, strategy):
        """Test exact team name match."""
        result = strategy.match("kommandos abilities", ["kommandos", "abilities"])
        assert "Kommandos" in result

    def test_fuzzy_team_name_match_typo(self, strategy):
        """Test fuzzy match with typo."""
        # "deathwach" should match "Deathwatch"
        result = strategy.match("deathwach abilities", ["deathwach", "abilities"])
        assert "Deathwatch" in result

    def test_fuzzy_team_name_match_singular(self, strategy):
        """Test fuzzy match with singular form."""
        # "kommando" should match "Kommandos"
        result = strategy.match("kommando", ["kommando"])
        assert "Kommandos" in result

    def test_fuzzy_team_name_match_plural(self, strategy):
        """Test fuzzy match with plural form."""
        # "kasrkins" should match "Kasrkin"
        result = strategy.match("kasrkins", ["kasrkins"])
        assert "Kasrkin" in result

    def test_no_fuzzy_match_below_threshold(self, strategy):
        """Test no match when similarity is below threshold."""
        # "marines" is too different from any team name
        result = strategy.match("marines", ["marines"])
        # Should not match any team (or very unlikely)
        assert len(result) <= 1  # Might match something by chance, but unlikely

    def test_short_word_skipped(self, strategy):
        """Test short words (< 4 chars) are skipped."""
        result = strategy.match("the or and", ["the", "or", "and"])
        assert len(result) == 0


class TestStrategyIntegration:
    """Integration tests for multiple strategies working together."""

    @pytest.fixture
    def operative_cache(self):
        """Operative cache."""
        return {
            "kommando": {
                "teams": ["Kommandos"],
                "words": ["kommando"],
                "has_role_words": False,
            },
        }

    @pytest.fixture
    def ability_cache(self):
        """Ability cache."""
        return {
            "ere go": {
                "teams": ["Kommandos"],
                "words": ["ere", "go"],
            },
        }

    def test_multiple_strategies_same_team(self, operative_cache, ability_cache):
        """Test multiple strategies matching the same team."""
        operative_strategy = OperativeMatchingStrategy(operative_cache)
        ability_strategy = AbilityMatchingStrategy(ability_cache)
        alias_strategy = AliasMatchingStrategy(TEAM_ALIASES)

        query_lower = "can kommando orks use ere we go"
        query_words = ["kommando", "orks", "ere", "go"]

        results = set()
        results.update(operative_strategy.match(query_lower, query_words))
        results.update(ability_strategy.match(query_lower, query_words))
        results.update(alias_strategy.match(query_lower, query_words))

        # Should match via operative, ability, and alias
        assert "Kommandos" in results

    def test_different_strategies_different_teams(self):
        """Test different strategies matching different teams."""
        operative_cache = {
            "kommando": {"teams": ["Kommandos"], "words": ["kommando"], "has_role_words": False},
            "pathfinder warrior": {
                "teams": ["Pathfinders"],
                "words": ["pathfinder", "warrior"],
                "has_role_words": True,
            },
        }

        operative_strategy = OperativeMatchingStrategy(operative_cache)
        alias_strategy = AliasMatchingStrategy(TEAM_ALIASES)

        query_lower = "kommando vs tau"
        query_words = ["kommando", "tau"]

        results = set()
        results.update(operative_strategy.match(query_lower, query_words))
        results.update(alias_strategy.match(query_lower, query_words))

        # Should match Kommandos (operative) and Tau teams (alias)
        assert "Kommandos" in results
        assert "Pathfinders" in results  # Tau alias
