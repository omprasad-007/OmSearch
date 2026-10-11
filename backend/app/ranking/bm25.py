from typing import Dict, Any


def build_bm25_search_query(
    query_str: str,
    page: int = 1,
    size: int = 10,
    language_filter: str | None = None,
    domain_filter: str | None = None,
) -> Dict[str, Any]:
    """
    Constructs an OpenSearch BM25 query with:
    - Title boost: 3.0
    - Snippet boost: 1.5
    - Content body: 1.0
    - Phrase matching boost for exact phrase occurrences
    - Snippet highlighting with <em> tags
    - Deterministic tie-breaking by [_score DESC, indexed_at DESC, id ASC]
    - Safe pagination offset calculation
    """
    from_offset = (page - 1) * size

    # Multi-match query across indexed text fields
    should_clauses = [
        # Multi-match with best_fields / most_fields
        {
            "multi_match": {
                "query": query_str,
                "fields": [
                    "title^3.0",
                    "title.english^3.0",
                    "snippet^1.5",
                    "content^1.0",
                    "content.english^1.0",
                ],
                "type": "most_fields",
                "operator": "or",
                "minimum_should_match": "1",
                "fuzziness": "AUTO",
                "prefix_length": 2,
            }
        },
        # Exact phrase match boost
        {
            "match_phrase": {
                "title": {
                    "query": query_str,
                    "boost": 4.0,
                    "slop": 1,
                }
            }
        },
        {
            "match_phrase": {
                "content": {
                    "query": query_str,
                    "boost": 1.5,
                    "slop": 2,
                }
            }
        },
    ]

    filter_clauses = []
    if language_filter:
        filter_clauses.append({"term": {"language": language_filter}})
    if domain_filter:
        filter_clauses.append({"term": {"domain": domain_filter}})

    query_body: Dict[str, Any] = {
        "from": from_offset,
        "size": size,
        "query": {
            "bool": {
                "must": [
                    {
                        "bool": {
                            "should": should_clauses,
                            "minimum_should_match": 1,
                        }
                    }
                ],
                "filter": filter_clauses,
            }
        },
        "highlight": {
            "fields": {
                "title": {
                    "number_of_fragments": 0,
                    "pre_tags": ["<mark>"],
                    "post_tags": ["</mark>"],
                },
                "content": {
                    "fragment_size": 160,
                    "number_of_fragments": 2,
                    "no_match_size": 160,
                    "pre_tags": ["<mark>"],
                    "post_tags": ["</mark>"],
                },
            }
        },
        # Deterministic tie-breaking
        "sort": [
            {"_score": {"order": "desc"}},
            {"indexed_at": {"order": "desc", "missing": "_last"}},
            {"id": {"order": "asc"}},
        ],
        "track_total_hits": True,
    }

    return query_body


def build_suggestions_query(prefix_query: str, size: int = 5) -> Dict[str, Any]:
    """
    Constructs an OpenSearch query for instant autocomplete / suggestions.
    Searches prefix on titles and returns top matching titles.
    """
    return {
        "size": size,
        "_source": ["title"],
        "query": {
            "bool": {
                "should": [
                    {
                        "match_phrase_prefix": {
                            "title": {
                                "query": prefix_query,
                                "max_expansions": 10,
                                "boost": 2.0,
                            }
                        }
                    },
                    {
                        "prefix": {
                            "title.keyword": {
                                "value": prefix_query.lower(),
                                "boost": 1.0,
                            }
                        }
                    },
                ],
                "minimum_should_match": 1,
            }
        },
        "sort": [
            {"_score": {"order": "desc"}},
            {"indexed_at": {"order": "desc"}},
        ],
    }
