from typing import Dict, List, Set, Optional


# Curated, unambiguous domain synonyms for technical search
SYNONYM_GROUPS: Dict[str, List[str]] = {
    "py": ["python"],
    "python": ["py"],
    "postgres": ["postgresql"],
    "postgresql": ["postgres"],
    "db": ["database"],
    "database": ["db"],
    "docs": ["documentation"],
    "documentation": ["docs"],
    "api": ["interface", "endpoint"],
    "auth": ["authentication"],
    "opensearch": ["elasticsearch"],
}


class SynonymExpander:
    """
    Controlled query synonym expander.
    Only expands unquoted search terms when safe, avoiding semantic drift.
    """

    def __init__(self, mappings: Optional[Dict[str, List[str]]] = None):
        self.mappings = mappings or SYNONYM_GROUPS

    def get_synonyms(self, term: str) -> List[str]:
        return self.mappings.get(term.lower(), [])

    def expand_tokens(self, tokens: List[str], max_expansions_per_term: int = 1) -> List[str]:
        expanded = []
        for t in tokens:
            syns = self.get_synonyms(t)
            if syns:
                expanded.extend(syns[:max_expansions_per_term])
        return list(set(expanded))
