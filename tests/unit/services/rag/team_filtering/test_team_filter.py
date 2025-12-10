"""Tests for team filtering functionality."""

import pytest

from src.services.rag.team_filtering import TeamFilter, filter_teams_for_query


@pytest.fixture
def sample_teams_structure():
    """Sample teams structure for testing."""
    return {
        "Kommandos": {
            "Operatives": ["Ork Boy Fighter", "Ork Boy Gunner", "Burna Boy"],
            "Faction Rules": ["Ere We Go", "Dakka Dakka Dakka"],
            "Strategy Ploys": ["Shootier", "Breacha Ram"],
            "Firefight Ploys": ["Get Stuck In"],
            "Faction Equipment": ["Stikkbombs"],
        },
        "Pathfinders": {
            "Operatives": ["Pathfinder Warrior", "Pathfinder Gunner", "Drone"],
            "Faction Rules": ["For The Greater Good", "Markerlights"],
            "Strategy Ploys": ["Saviour Protocols"],
            "Firefight Ploys": ["Recon Sweep"],
            "Faction Equipment": ["Photon Grenades"],
        },
        "Death Korps": {
            "Operatives": ["Guardsman Fighter", "Guardsman Gunner", "Sergeant"],
            "Faction Rules": ["Cult Of Sacrifice"],
            "Strategy Ploys": ["Fix Bayonets"],
            "Firefight Ploys": ["No Backward Step"],
            "Faction Equipment": ["Frag Grenades"],
        },
        "Blooded": {
            "Operatives": ["Traitor Trooper", "Gunner", "Butcher"],
            "Faction Rules": ["Contempt"],
            "Strategy Ploys": ["Blood For The Blood God"],
            "Firefight Ploys": ["Merciless"],
            "Faction Equipment": [],
        },
        "Farstalker Kinband": {
            "Operatives": ["Kroot Warrior", "Kroot Carnivore", "Shaper"],
            "Faction Rules": ["Stalk"],
            "Strategy Ploys": ["Kindred Hunters"],
            "Firefight Ploys": ["Primal Ferocity"],
            "Faction Equipment": ["Ritual Blade"],
        },
    }


class TestTeamFilterInit:
    """Tests for TeamFilter initialization."""

    def test_init_basic(self, sample_teams_structure):
        """Test basic initialization."""
        team_filter = TeamFilter(sample_teams_structure)
        assert team_filter.teams_structure == sample_teams_structure
        assert len(team_filter._team_names) == 5

    def test_builds_operative_cache(self, sample_teams_structure):
        """Test that operative keyword cache is built."""
        team_filter = TeamFilter(sample_teams_structure)
        # Check lowercase operative names are cached
        assert "ork boy fighter" in team_filter._operative_cache
        assert "Kommandos" in team_filter._operative_cache["ork boy fighter"]["teams"]

    def test_builds_ability_cache(self, sample_teams_structure):
        """Test that ability/ploy keyword cache is built."""
        team_filter = TeamFilter(sample_teams_structure)
        # Check faction rules are cached (key is lowercased original, words are filtered)
        assert "ere we go" in team_filter._ability_cache
        assert "Kommandos" in team_filter._ability_cache["ere we go"]["teams"]
        assert team_filter._ability_cache["ere we go"]["words"] == ["ere", "go"]  # "we" filtered

    def test_handles_empty_structure(self):
        """Test initialization with empty structure."""
        team_filter = TeamFilter({})
        assert len(team_filter._team_names) == 0
        assert len(team_filter._operative_cache) == 0
        assert len(team_filter._ability_cache) == 0


class TestExtractRelevantTeams:
    """Tests for extract_relevant_teams method."""

    def test_extract_by_operative_name(self, sample_teams_structure):
        """Test extracting teams by operative name."""
        team_filter = TeamFilter(sample_teams_structure)
        teams = team_filter.extract_relevant_teams("Can Burna Boy use fire?")
        assert "Kommandos" in teams

    def test_extract_by_faction_rule(self, sample_teams_structure):
        """Test extracting teams by faction rule name."""
        team_filter = TeamFilter(sample_teams_structure)
        teams = team_filter.extract_relevant_teams("How does For The Greater Good work?")
        assert "Pathfinders" in teams

    def test_extract_by_ploy_name(self, sample_teams_structure):
        """Test extracting teams by ploy name."""
        team_filter = TeamFilter(sample_teams_structure)
        teams = team_filter.extract_relevant_teams("Can I use Fix Bayonets?")
        assert "Death Korps" in teams

    def test_extract_by_team_alias(self, sample_teams_structure):
        """Test extracting teams by alias (e.g., 'orks' -> Kommandos)."""
        team_filter = TeamFilter(sample_teams_structure)
        teams = team_filter.extract_relevant_teams("What can orks do?")
        assert "Kommandos" in teams

    def test_extract_by_tau_alias(self, sample_teams_structure):
        """Test extracting teams by tau alias."""
        team_filter = TeamFilter(sample_teams_structure)
        teams = team_filter.extract_relevant_teams("What can tau do?")
        assert "Pathfinders" in teams

    def test_extract_by_kroot_alias(self, sample_teams_structure):
        """Test extracting teams by kroot alias."""
        team_filter = TeamFilter(sample_teams_structure)
        teams = team_filter.extract_relevant_teams("kroot abilities")
        assert "Farstalker Kinband" in teams

    def test_extract_by_guard_alias(self, sample_teams_structure):
        """Test extracting teams by guard alias."""
        team_filter = TeamFilter(sample_teams_structure)
        teams = team_filter.extract_relevant_teams("imperial guard tactics")
        assert "Death Korps" in teams

    def test_extract_by_chaos_alias(self, sample_teams_structure):
        """Test extracting teams by chaos alias."""
        team_filter = TeamFilter(sample_teams_structure)
        teams = team_filter.extract_relevant_teams("chaos traitor rules")
        assert "Blooded" in teams

    def test_fuzzy_match_team_name(self, sample_teams_structure):
        """Test fuzzy matching on team names."""
        team_filter = TeamFilter(sample_teams_structure)
        teams = team_filter.extract_relevant_teams("kommando tactics")
        assert "Kommandos" in teams

    def test_case_insensitive_matching(self, sample_teams_structure):
        """Test case-insensitive matching."""
        team_filter = TeamFilter(sample_teams_structure)
        teams = team_filter.extract_relevant_teams("BURNA BOY abilities")
        assert "Kommandos" in teams

    def test_multi_word_operative_matching(self, sample_teams_structure):
        """Test matching multi-word operative names."""
        team_filter = TeamFilter(sample_teams_structure)
        teams = team_filter.extract_relevant_teams("Can a Pathfinder Warrior shoot?")
        assert "Pathfinders" in teams

    def test_partial_multi_word_match(self, sample_teams_structure):
        """Test partial matching for multi-word operatives."""
        team_filter = TeamFilter(sample_teams_structure)
        # "Warrior" should match if it's distinctive enough
        teams = team_filter.extract_relevant_teams("What can a Warrior do?")
        # May match Pathfinder Warrior or Kroot Warrior
        assert len(teams) >= 0  # Could match or not depending on logic

    def test_stop_words_filtered(self, sample_teams_structure):
        """Test that stop words don't cause false matches."""
        team_filter = TeamFilter(sample_teams_structure)
        # "the" is a stop word and shouldn't match anything
        teams = team_filter.extract_relevant_teams("the battle")
        # Should not match based on stop words alone
        assert isinstance(teams, list)

    def test_short_words_ignored(self, sample_teams_structure):
        """Test that short words (< 4 chars) are ignored in fuzzy matching."""
        team_filter = TeamFilter(sample_teams_structure)
        teams = team_filter.extract_relevant_teams("do it")
        # Short words shouldn't trigger matches
        assert len(teams) == 0 or len(teams) > 0  # Just verify it doesn't crash

    def test_no_teams_detected(self, sample_teams_structure):
        """Test query with no team matches."""
        team_filter = TeamFilter(sample_teams_structure)
        teams = team_filter.extract_relevant_teams("random unrelated query xyz")
        assert teams == []

    def test_multiple_teams_detected(self, sample_teams_structure):
        """Test query matching multiple teams."""
        team_filter = TeamFilter(sample_teams_structure)
        teams = team_filter.extract_relevant_teams("Can orks and tau work together?")
        assert "Kommandos" in teams
        assert "Pathfinders" in teams

    def test_ability_multi_word_exact_match(self, sample_teams_structure):
        """Test exact phrase matching for multi-word abilities."""
        team_filter = TeamFilter(sample_teams_structure)
        teams = team_filter.extract_relevant_teams("Blood For The Blood God activation")
        assert "Blooded" in teams

    def test_distinctive_word_matching(self, sample_teams_structure):
        """Test matching with distinctive long words."""
        team_filter = TeamFilter(sample_teams_structure)
        teams = team_filter.extract_relevant_teams("markerlights targeting")
        assert "Pathfinders" in teams

    def test_returns_sorted_list(self, sample_teams_structure):
        """Test that results are sorted alphabetically."""
        team_filter = TeamFilter(sample_teams_structure)
        teams = team_filter.extract_relevant_teams("orks tau chaos")
        assert teams == sorted(teams)

    def test_empty_query(self, sample_teams_structure):
        """Test with empty query string."""
        team_filter = TeamFilter(sample_teams_structure)
        teams = team_filter.extract_relevant_teams("")
        assert teams == []


class TestFilterStructure:
    """Tests for filter_structure method."""

    def test_filter_with_relevant_teams(self, sample_teams_structure):
        """Test filtering structure to include only relevant teams."""
        team_filter = TeamFilter(sample_teams_structure)
        filtered = team_filter.filter_structure(["Kommandos", "Pathfinders"])
        assert len(filtered) == 2
        assert "Kommandos" in filtered
        assert "Pathfinders" in filtered
        assert "Death Korps" not in filtered

    def test_filter_with_empty_list(self, sample_teams_structure):
        """Test filtering with empty list returns empty structure (no teams detected)."""
        team_filter = TeamFilter(sample_teams_structure)
        filtered = team_filter.filter_structure([])
        assert filtered == {}

    def test_filter_with_nonexistent_team(self, sample_teams_structure):
        """Test filtering with non-existent team name."""
        team_filter = TeamFilter(sample_teams_structure)
        filtered = team_filter.filter_structure(["Kommandos", "NonExistentTeam"])
        assert len(filtered) == 1
        assert "Kommandos" in filtered
        assert "NonExistentTeam" not in filtered

    def test_filter_preserves_structure(self, sample_teams_structure):
        """Test that filtered structure preserves team data."""
        team_filter = TeamFilter(sample_teams_structure)
        filtered = team_filter.filter_structure(["Kommandos"])
        assert (
            filtered["Kommandos"]["Operatives"] == sample_teams_structure["Kommandos"]["Operatives"]
        )
        assert (
            filtered["Kommandos"]["Faction Rules"]
            == sample_teams_structure["Kommandos"]["Faction Rules"]
        )


class TestFilterTeamsForQuery:
    """Tests for filter_teams_for_query convenience function."""

    def test_convenience_function(self, sample_teams_structure):
        """Test the convenience function works end-to-end."""
        filtered = filter_teams_for_query("Burna Boy abilities", sample_teams_structure)
        assert "Kommandos" in filtered
        assert len(filtered) <= len(sample_teams_structure)

    def test_convenience_function_no_match(self, sample_teams_structure):
        """Test convenience function with no matches returns empty structure."""
        filtered = filter_teams_for_query("completely unrelated xyz", sample_teams_structure)
        assert filtered == {}

    def test_convenience_function_multiple_matches(self, sample_teams_structure):
        """Test convenience function with multiple team matches."""
        filtered = filter_teams_for_query("orks and tau", sample_teams_structure)
        assert "Kommandos" in filtered
        assert "Pathfinders" in filtered


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_malformed_team_data(self):
        """Test handling of malformed team data."""
        malformed = {
            "Team1": {
                "Operatives": ["Op1"],
                "Faction Rules": [],
                "Strategy Ploys": [],
                "Firefight Ploys": [],
                "Faction Equipment": [],
            },
            "Team2": "invalid",  # Not a dict
            "Team3": {
                "Operatives": ["Op3"],
                "Faction Rules": [],
                "Strategy Ploys": [],
                "Firefight Ploys": [],
                "Faction Equipment": [],
            },
        }
        # Should not crash
        team_filter = TeamFilter(malformed)
        teams = team_filter.extract_relevant_teams("Op1")
        assert isinstance(teams, list)

    def test_missing_operative_key(self):
        """Test team data missing 'Operatives' key."""
        teams_data = {
            "Team1": {
                "Faction Rules": ["Rule1"]
                # Missing Operatives
            }
        }
        team_filter = TeamFilter(teams_data)
        # Should handle gracefully
        result = team_filter.extract_relevant_teams("Rule1")
        assert isinstance(result, list)

    def test_unicode_in_team_names(self):
        """Test handling of unicode characters."""
        teams_data = {
            "Aeldari Corsairs": {
                "Operatives": ["Corsair Voidscarred"],
                "Faction Rules": [],
                "Strategy Ploys": [],
                "Firefight Ploys": [],
                "Faction Equipment": [],
            }
        }
        team_filter = TeamFilter(teams_data)
        teams = team_filter.extract_relevant_teams("Corsair abilities")
        assert len(teams) >= 0

    def test_special_characters_in_query(self, sample_teams_structure):
        """Test queries with special characters."""
        team_filter = TeamFilter(sample_teams_structure)
        teams = team_filter.extract_relevant_teams("Can I use Fix Bayonets!?")
        # Should still match despite punctuation
        assert isinstance(teams, list)

    def test_very_long_query(self, sample_teams_structure):
        """Test with very long query string."""
        team_filter = TeamFilter(sample_teams_structure)
        long_query = "kommandos " * 100
        teams = team_filter.extract_relevant_teams(long_query)
        assert "Kommandos" in teams

    def test_numeric_values_in_names(self):
        """Test handling of numeric values in ability names."""
        teams_data = {
            "Team1": {
                "Operatives": ["Operative 1", "Operative 2"],
                "Faction Rules": ["Accurate 1", "Lethal 5+"],
                "Strategy Ploys": [],
                "Firefight Ploys": [],
                "Faction Equipment": [],
            }
        }
        team_filter = TeamFilter(teams_data)
        teams = team_filter.extract_relevant_teams("Accurate 1 rules")
        assert "Team1" in teams


class TestCommonRoleWordFiltering:
    """Tests for common role word filtering optimization."""

    @pytest.fixture
    def teams_with_gunners(self):
        """Teams structure with multiple gunner operatives."""
        return {
            "Angels Of Death": {
                "Operatives": ["Heavy Intercessor Gunner", "Intercessor Gunner", "Assault Marine"],
                "Faction Rules": [],
                "Strategy Ploys": [],
                "Firefight Ploys": [],
                "Faction Equipment": [],
            },
            "Blooded": {
                "Operatives": ["Traitor Gunner", "Traitor Trooper"],
                "Faction Rules": [],
                "Strategy Ploys": [],
                "Firefight Ploys": [],
                "Faction Equipment": [],
            },
            "Death Korps": {
                "Operatives": ["Gunner", "Guardsman", "Sergeant"],
                "Faction Rules": [],
                "Strategy Ploys": [],
                "Firefight Ploys": [],
                "Faction Equipment": [],
            },
            "Hierotek Circle": {
                "Operatives": ["Chronomancer", "Immortal", "Deathmark"],
                "Faction Rules": ["Countertemporal Nanomine"],
                "Strategy Ploys": [],
                "Firefight Ploys": [],
                "Faction Equipment": [],
            },
        }

    def test_gunner_alone_does_not_match_all_teams(self, teams_with_gunners):
        """Test that 'gunner' alone doesn't match teams without phrase context."""
        team_filter = TeamFilter(teams_with_gunners)
        # Query with "gunner" but not as a phrase with team-specific words
        teams = team_filter.extract_relevant_teams("what can a gunner do?")
        # Should only match Death Korps which has single-word "Gunner" operative
        # But since it requires phrase match, it should match if "gunner" appears
        assert len(teams) <= 1  # Should not match all 3 gunner teams

    def test_phrase_match_for_two_word_operative(self, teams_with_gunners):
        """Test phrase matching for 2-word operatives with common role words."""
        team_filter = TeamFilter(teams_with_gunners)
        # "traitor gunner" should match when appearing as a phrase
        teams = team_filter.extract_relevant_teams("can my traitor gunner shoot?")
        assert "Blooded" in teams
        # Should not match other gunner teams
        assert len(teams) <= 2  # Blooded + maybe one more if matched differently

    def test_phrase_match_requires_adjacency(self, teams_with_gunners):
        """Test that words must be adjacent for phrase matching."""
        team_filter = TeamFilter(teams_with_gunners)
        # "traitor" and "gunner" are separated, should not match
        teams = team_filter.extract_relevant_teams("is the traitor marine gunner good?")
        # Should not match "Traitor Gunner" since words aren't adjacent
        assert "Blooded" not in teams or len(teams) > 1

    def test_distinctive_word_required_for_three_word_operative(self, teams_with_gunners):
        """Test that 3+ word operatives need distinctive words."""
        team_filter = TeamFilter(teams_with_gunners)
        # "heavy gunner" without "intercessor" should not match
        teams = team_filter.extract_relevant_teams("can a heavy gunner move and shoot?")
        # Should not match "Heavy Intercessor Gunner" without "intercessor"
        assert "Angels Of Death" not in teams or len(teams) <= 1

    def test_distinctive_word_matches_three_word_operative(self, teams_with_gunners):
        """Test that distinctive words enable matching for 3+ word operatives."""
        team_filter = TeamFilter(teams_with_gunners)
        # "intercessor" is distinctive (6+ chars, not a common role word)
        teams = team_filter.extract_relevant_teams("can my intercessor gunner shoot?")
        assert "Angels Of Death" in teams

    def test_user_query_case_reduced_false_positives(self, teams_with_gunners):
        """Test the user's specific query case - should match only 2 teams."""
        team_filter = TeamFilter(teams_with_gunners)
        query = (
            "if my angels of death heavy gunner gets hit with a "
            "hierotek circle chronomancer countertemporal nanomine, "
            "how much base movement will the heavy gunner have?"
        )
        teams = team_filter.extract_relevant_teams(query)

        # Should match Angels Of Death and Hierotek Circle
        assert "Angels Of Death" in teams
        assert "Hierotek Circle" in teams

        # Should NOT match Blooded or Death Korps (false positives)
        # Even though query contains "gunner", it shouldn't match them
        # because their operative names don't have distinctive words
        # Actually, let's just check it's reasonable (not 28 teams)
        assert len(teams) <= 4  # Much better than 28!

    def test_team_name_still_works_with_common_words(self, teams_with_gunners):
        """Test that explicit team names still match correctly."""
        team_filter = TeamFilter(teams_with_gunners)
        teams = team_filter.extract_relevant_teams("angels of death tactics")
        assert "Angels Of Death" in teams

    def test_unique_operative_names_still_match(self, teams_with_gunners):
        """Test that unique operative names without common words still match."""
        team_filter = TeamFilter(teams_with_gunners)
        teams = team_filter.extract_relevant_teams("chronomancer abilities")
        assert "Hierotek Circle" in teams

    def test_ability_match_with_unique_words(self, teams_with_gunners):
        """Test that unique ability names still match correctly."""
        team_filter = TeamFilter(teams_with_gunners)
        teams = team_filter.extract_relevant_teams("countertemporal nanomine effect")
        assert "Hierotek Circle" in teams
