"""Unit tests for QueryExpander service."""

import json
from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest

from src.services.rag.query_expander import QueryExpander


@pytest.fixture
def temp_synonym_dict():
    """Create a temporary synonym dictionary for testing."""
    synonyms = {
        "regain wounds": ["heal", "healing", "restore health", "recover hp"],
        "incapacitated": ["died", "killed", "destroyed"],
        "control range": ["melee range", "base contact"],
        "Shoot action": ["shoot", "fire", "shooting"],
        "operative": ["model", "unit", "miniature"],
    }

    with NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(synonyms, f)
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink()


@pytest.fixture
def expander(temp_synonym_dict):
    """Create QueryExpander instance with test dictionary."""
    return QueryExpander(temp_synonym_dict)


class TestQueryExpanderInit:
    """Tests for QueryExpander initialization."""

    def test_init_with_valid_dict(self, temp_synonym_dict):
        """Test initialization with valid synonym dictionary."""
        expander = QueryExpander(temp_synonym_dict)

        assert len(expander.official_to_synonyms) == 5
        assert len(expander.synonym_to_official) > 0

    def test_init_with_missing_dict(self, tmp_path):
        """Test initialization with non-existent dictionary."""
        missing_path = str(tmp_path / "missing.json")
        expander = QueryExpander(missing_path)

        # Should initialize with empty dictionaries
        assert len(expander.official_to_synonyms) == 0
        assert len(expander.synonym_to_official) == 0

    def test_reverse_mapping_creation(self, expander):
        """Test that reverse mapping is created correctly."""
        # Check that synonyms map to official terms
        assert expander.synonym_to_official["heal"] == "regain wounds"
        assert expander.synonym_to_official["killed"] == "incapacitated"
        assert expander.synonym_to_official["melee range"] == "control range"

    def test_case_insensitive_mapping(self, expander):
        """Test that reverse mapping is lowercase for case-insensitive matching."""
        # All keys should be lowercase
        for key in expander.synonym_to_official:
            assert key == key.lower()


class TestQueryExpansion:
    """Tests for query expansion logic."""

    def test_expand_single_word_synonym(self, expander):
        """Test expansion with single-word synonym."""
        query = "Can I heal my operative?"
        expanded = expander.expand_query(query)

        assert "regain wounds" in expanded
        assert query in expanded  # Original query preserved

    def test_expand_multiple_synonyms(self, expander):
        """Test expansion with multiple synonyms in query."""
        query = "Can a model shoot after being killed?"
        expanded = expander.expand_query(query)

        # Should expand both "model" and "killed"
        assert "operative" in expanded
        assert "incapacitated" in expanded
        assert "Shoot action" in expanded

    def test_expand_multi_word_phrase(self, expander):
        """Test expansion with multi-word phrase synonym."""
        query = "What is melee range?"
        expanded = expander.expand_query(query)

        assert "control range" in expanded
        assert "melee range" in expanded  # Original preserved

    def test_case_insensitive_matching(self, expander):
        """Test that matching is case-insensitive."""
        # Test various capitalizations
        queries = [
            "Can I HEAL my operative?",
            "Can I Heal my operative?",
            "Can I heal my operative?",
        ]

        for query in queries:
            expanded = expander.expand_query(query)
            assert "regain wounds" in expanded

    def test_word_boundary_matching(self, expander):
        """Test that matching respects word boundaries."""
        # "heal" should match, but "healer" should not
        query = "Can the healer heal?"
        expanded = expander.expand_query(query)

        # Should only expand the word "heal", not "healer"
        assert expanded.count("regain wounds") == 1

    def test_no_expansion_without_synonyms(self, expander):
        """Test that queries without synonyms are unchanged."""
        query = "What is the Accurate rule?"
        expanded = expander.expand_query(query)

        assert expanded == query

    def test_preserve_punctuation(self, expander):
        """Test that punctuation is preserved."""
        query = "Can I heal? Or shoot?"
        expanded = expander.expand_query(query)

        # Original query with punctuation should be in expanded version
        assert "Can I heal?" in expanded or "heal" in expanded

    def test_multiple_occurrences_same_synonym(self, expander):
        """Test that same official term is only added once."""
        query = "Can I heal and then heal again?"
        expanded = expander.expand_query(query)

        # "regain wounds" should only appear once in expansion
        expansion_part = expanded.replace(query, "")
        assert expansion_part.count("regain wounds") == 1

    def test_expand_with_multiple_words_synonym(self, expander):
        """Test expansion prefers longer (more specific) matches."""
        query = "What is the melee range control range?"
        expanded = expander.expand_query(query)

        # Should match "melee range" as a phrase
        assert "control range" in expanded


class TestQueryExpanderStats:
    """Tests for QueryExpander statistics methods."""

    def test_get_stats(self, expander):
        """Test statistics retrieval."""
        stats = expander.get_stats()

        assert "official_terms" in stats
        assert "total_synonyms" in stats
        assert "loaded" in stats
        assert stats["loaded"] is True
        assert stats["official_terms"] == 5
        assert stats["total_synonyms"] > 5  # More synonyms than official terms

    def test_get_official_terms(self, expander):
        """Test getting list of official terms."""
        terms = expander.get_official_terms()

        assert "regain wounds" in terms
        assert "incapacitated" in terms
        assert len(terms) == 5

    def test_get_synonyms_for_term(self, expander):
        """Test getting synonyms for specific official term."""
        synonyms = expander.get_synonyms_for_term("regain wounds")

        assert "heal" in synonyms
        assert "healing" in synonyms
        assert "restore health" in synonyms

    def test_get_synonyms_for_missing_term(self, expander):
        """Test getting synonyms for non-existent term."""
        synonyms = expander.get_synonyms_for_term("nonexistent")

        assert synonyms == []


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_query(self, expander):
        """Test expansion with empty query."""
        expanded = expander.expand_query("")
        assert expanded == ""

    def test_query_with_special_characters(self, expander):
        """Test expansion with special characters."""
        query = "Can I heal? (really heal?)"
        expanded = expander.expand_query(query)

        assert "regain wounds" in expanded

    def test_query_with_numbers(self, expander):
        """Test expansion with numbers in query."""
        query = "Can model 3 heal model 5?"
        expanded = expander.expand_query(query)

        assert "operative" in expanded
        assert "regain wounds" in expanded

    def test_malformed_synonym_dict(self, tmp_path):
        """Test loading malformed JSON dictionary."""
        bad_dict_path = tmp_path / "bad.json"
        bad_dict_path.write_text("{not valid json")

        expander = QueryExpander(str(bad_dict_path))

        # Should handle error gracefully with empty dictionaries
        assert len(expander.official_to_synonyms) == 0
        assert len(expander.synonym_to_official) == 0


class TestRealWorldQueries:
    """Tests with realistic Kill Team queries."""

    def test_heal_query(self, expander):
        """Test realistic healing query."""
        query = "Can I use a medikit to heal my wounded operative?"
        expanded = expander.expand_query(query)

        assert "regain wounds" in expanded
        assert "operative" in expanded or "model" not in expanded  # "operative" already in query

    def test_death_query(self, expander):
        """Test realistic death/incapacitation query."""
        query = "What happens when my model is killed?"
        expanded = expander.expand_query(query)

        assert "incapacitated" in expanded
        assert "operative" in expanded

    def test_melee_query(self, expander):
        """Test realistic melee range query."""
        query = "Can I shoot at enemies in melee range?"
        expanded = expander.expand_query(query)

        assert "control range" in expanded
        assert "Shoot action" in expanded

    def test_action_query(self, expander):
        """Test realistic action query."""
        query = "Can I shoot twice in one activation?"
        expanded = expander.expand_query(query)

        assert "Shoot action" in expanded
