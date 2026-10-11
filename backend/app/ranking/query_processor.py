import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Tuple


@dataclass
class ProcessedQuery:
    raw_query: str
    normalized_query: str
    tokens: List[str]
    quoted_phrases: List[str]
    intent: str  # informational, navigational, technical, freshness, general
    intent_confidence: float
    has_technical_identifiers: bool
    spelling_suggestion: Optional[str] = None
    expanded_synonyms: List[str] = field(default_factory=list)


# Known technical keywords, file extensions, and language tokens
TECHNICAL_PATTERNS = [
    re.compile(r"\b(def|class|import|async|await|function|return|struct|fn|var|const|let)\b", re.I),
    re.compile(r"\b(api|http|https|json|sql|xml|html|css|orm|rest|grpc|crud|oauth|jwt)\b", re.I),
    re.compile(r"\b(error|exception|traceback|syntaxerror|typeerror|nullpointer|failed|errno)\b", re.I),
    re.compile(r"\b\w+\.(py|js|ts|tsx|jsx|rs|go|cpp|c|java|sql|sh|yaml|yml|json|md)\b", re.I),
    re.compile(r"[a-zA-Z0-9_]+::[a-zA-Z0-9_]+|[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+\(\)"),  # method calls
]

NAVIGATIONAL_PATTERNS = [
    re.compile(r"\b(docs|documentation|official|homepage|download|github|repo|login|signup|portal)\b", re.I),
    re.compile(r"^[a-zA-Z0-9-]+\.(com|org|io|dev|net|edu|gov)(/.*)?$", re.I),  # direct domain-like query
]

FRESHNESS_PATTERNS = [
    re.compile(r"\b(latest|recent|new in|release|releases|updates|changelog|current|today|roadmap|202[4-9])\b", re.I),
]

INFORMATIONAL_PATTERNS = [
    re.compile(r"\b(what is|how to|why does|guide|tutorial|overview|example|introduction|learn|difference between)\b", re.I),
]


class QueryProcessor:
    """
    Lightweight, modular query processor handling:
    1. Normalization & quoted phrase extraction.
    2. Rule-based intent classification.
    3. Technical identifier detection.
    4. Conservative spelling correction using known lexicon.
    """

    def __init__(self, vocabulary: Optional[Set[str]] = None):
        self.vocabulary = vocabulary or {
            "python", "opensearch", "postgresql", "fastapi", "react", "sqlite",
            "database", "indexing", "algorithm", "algorithmics", "framework",
            "tutorial", "documentation", "query", "search", "engine", "schema",
            "serverless", "component", "interface", "protocol", "status",
        }

    def process(self, raw_query: str) -> ProcessedQuery:
        clean_raw = raw_query.strip()
        if not clean_raw:
            return ProcessedQuery(
                raw_query="",
                normalized_query="",
                tokens=[],
                quoted_phrases=[],
                intent="general",
                intent_confidence=1.0,
                has_technical_identifiers=False,
            )

        # 1. Unicode NFKC normalization
        norm_text = unicodedata.normalize("NFKC", clean_raw)

        # 2. Extract quoted phrases: "search term"
        quoted_phrases = [
            m.strip() for m in re.findall(r'"([^"]+)"', norm_text) if m.strip()
        ]

        # 3. Normalized text (remove quotes but preserve inner terms)
        clean_no_quotes = re.sub(r'["\']', " ", norm_text)
        # Collapse multiple spaces
        normalized = " ".join(clean_no_quotes.split())

        # 4. Tokenization: split on whitespace while keeping technical characters
        tokens = [t.lower() for t in normalized.split() if t]

        # 5. Technical identifier detection
        has_tech = any(pattern.search(clean_raw) for pattern in TECHNICAL_PATTERNS) or any(
            "_" in t or "." in t or "::" in t for t in tokens
        )

        # 6. Intent classification
        intent, confidence = self._classify_intent(clean_raw, tokens)

        # 7. Conservative spelling suggestion
        suggestion = self._generate_spelling_suggestion(tokens)

        return ProcessedQuery(
            raw_query=clean_raw,
            normalized_query=normalized.lower(),
            tokens=tokens,
            quoted_phrases=quoted_phrases,
            intent=intent,
            intent_confidence=confidence,
            has_technical_identifiers=has_tech,
            spelling_suggestion=suggestion,
        )

    def _classify_intent(self, raw_query: str, tokens: List[str]) -> Tuple[str, float]:
        q_lower = raw_query.lower()

        # Score matching rules
        tech_score = sum(1 for p in TECHNICAL_PATTERNS if p.search(q_lower))
        nav_score = sum(1 for p in NAVIGATIONAL_PATTERNS if p.search(q_lower))
        fresh_score = sum(1 for p in FRESHNESS_PATTERNS if p.search(q_lower))
        info_score = sum(1 for p in INFORMATIONAL_PATTERNS if p.search(q_lower))

        # Check intent priority
        if fresh_score > 0 and fresh_score >= max(nav_score, info_score):
            return "freshness", min(0.9, 0.6 + (fresh_score * 0.15))
        if nav_score > 0 and nav_score >= max(tech_score, info_score):
            return "navigational", min(0.95, 0.7 + (nav_score * 0.15))
        if info_score > 0 and info_score >= tech_score:
            return "informational", min(0.9, 0.6 + (info_score * 0.15))
        if tech_score > 0:
            return "technical", min(0.9, 0.6 + (tech_score * 0.15))

        return "general", 0.5

    def _generate_spelling_suggestion(self, tokens: List[str]) -> Optional[str]:
        """
        Produce a suggestion only when a single word differs from a known vocabulary word
        by edit distance 1 or transposition, without touching technical identifiers.
        """
        corrected = []
        any_changed = False

        for t in tokens:
            # Skip short words, numbers, and technical identifiers
            if len(t) <= 3 or t.isdigit() or "_" in t or "." in t:
                corrected.append(t)
                continue

            if t in self.vocabulary:
                corrected.append(t)
                continue

            # Look for closest match with Levenshtein distance <= 1
            best_match = None
            for candidate in self.vocabulary:
                if self._levenshtein_distance(t, candidate) == 1:
                    best_match = candidate
                    break

            if best_match:
                corrected.append(best_match)
                any_changed = True
            else:
                corrected.append(t)

        if any_changed:
            return " ".join(corrected)
        return None

    @staticmethod
    def _levenshtein_distance(s1: str, s2: str) -> int:
        if abs(len(s1) - len(s2)) > 1:
            return 2  # Prune early
        if s1 == s2:
            return 0
        if len(s1) == 0:
            return len(s2)
        if len(s2) == 0:
            return len(s1)

        v0 = list(range(len(s2) + 1))
        v1 = [0] * (len(s2) + 1)

        for i in range(len(s1)):
            v1[0] = i + 1
            for j in range(len(s2)):
                cost = 0 if s1[i] == s2[j] else 1
                v1[j + 1] = min(v1[j] + 1, v0[j + 1] + 1, v0[j] + cost)
            v0, v1 = v1, v0

        return v0[len(s2)]
