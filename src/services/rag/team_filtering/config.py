"""Configuration constants for team filtering.

This module centralizes all configuration values used in team filtering:
- Fuzzy matching thresholds
- Stop words for filtering
- Team aliases for faction abbreviations
- Common role words requiring stricter matching
"""

# Fuzzy matching threshold (0-100)
# Used by rapidfuzz to determine minimum similarity for matches
TEAM_MATCH_THRESHOLD = 80

# Minimum word length for matching (characters)
# Words shorter than this are ignored during matching
MIN_WORD_LENGTH = 4

# Distinctive word length threshold (characters)
# Words this length or longer are considered "distinctive" in operative names
DISTINCTIVE_WORD_LENGTH = 6

# Stop words to filter out (common English words with low semantic value)
# These appear in ability/ploy names but cause false positives when matching
STOP_WORDS = {
    # Articles
    "the",
    "a",
    "an",
    "this",
    "these",
    "those",
    # Prepositions
    "from",
    "with",
    "for",
    "before",
    "after",
    "into",
    "onto",
    "upon",
    "over",
    "under",
    "through",
    "across",
    "along",
    "behind",
    "beyond",
    "near",
    "beside",
    "of",
    "to",
    "in",
    "on",
    "at",
    # Conjunctions
    "and",
    "or",
    "but",
    "that",
    "thus",
    "then",
    "than",
    "as",
    "if",
    "when",
    "where",
    # Pronouns
    "his",
    "her",
    "its",
    "their",
    "your",
    "my",
    "our",
    "it",
    "he",
    "she",
    "they",
    "we",
    # Common verbs (auxiliary/modal and 'be' forms)
    "would",
    "could",
    "should",
    "will",
    "can",
    "may",
    "might",
    "must",
    "shall",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    # Quantifiers
    "all",
    "any",
    "some",
    "few",
    "many",
    "much",
    "more",
    "most",
    "less",
    "least",
    # Other common words
    "not",
    "no",
    "yes",
    "also",
    "just",
    "only",
    "very",
    "too",
    "so",
    "such",
}

# Common abbreviations and alternative names
# Maps faction/keyword abbreviations to full team names
TEAM_ALIASES = {
    "angels": ["Angels Of Death"],
    "space marines": [
        "Angels Of Death",
        "Deathwatch",
        "Phobos Strike Team",
        "Scout Squad",
        "Legionaries",
        "Plague Marines",
        "Nemesis Claw",
    ],
    "astartes": [
        "Angels Of Death",
        "Deathwatch",
        "Phobos Strike Team",
        "Scout Squad",
        "Legionaries",
        "Plague Marines",
        "Nemesis Claw",
    ],
    "chaos": [
        "Blooded",
        "Chaos Cult",
        "Legionaries",
        "Plague Marines",
        "Warpcoven",
        "Nemesis Claw",
        "Fellgor Ravagers",
        "Goremongers",
    ],
    "orks": ["Kommandos", "Wrecka Krew"],
    "tau": ["Pathfinders", "Vespid Stingwings", "Farstalker Kinband"],
    "kroot": ["Farstalker Kinband"],
    "kroots": ["Farstalker Kinband"],
    "eldar": [
        "Blades Of Khaine",
        "Corsair Voidscarred",
        "Void Dancer Troupe",
        "Hand Of The Archon",
        "Mandrakes",
    ],
    "aeldari": [
        "Blades Of Khaine",
        "Corsair Voidscarred",
        "Void Dancer Troupe",
        "Hand Of The Archon",
        "Mandrakes",
    ],
    "guard": ["Death Korps", "Kasrkin", "Tempestus Aquilons", "Imperial Navy Breachers"],
    "imperial guard": ["Death Korps", "Kasrkin", "Tempestus Aquilons", "Imperial Navy Breachers"],
    "hierotek": ["Hierotek Circle"],
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

# Common role words that appear in many operative names across teams
# These words require stricter matching to avoid false positives
COMMON_ROLE_WORDS = {
    "gunner",
    "warrior",
    "trooper",
    "leader",
    "sniper",
    "medic",
    "veteran",
    "fighter",
    "sergeant",
    "operative",
    "marine",
    "guard",
    "scout",
    "specialist",
    "mine",  # Common in equipment names (proximity mine, melta mine, etc.)
}
