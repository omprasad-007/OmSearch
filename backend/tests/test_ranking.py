from app.ranking.bm25 import build_bm25_search_query, build_suggestions_query


def test_build_bm25_query_structure():
    query = build_bm25_search_query("python open source", page=1, size=10)

    assert query["from"] == 0
    assert query["size"] == 10
    assert "bool" in query["query"]
    assert "highlight" in query
    assert "sort" in query

    # Check sort tie-breaking
    sort_fields = [list(s.keys())[0] for s in query["sort"]]
    assert sort_fields == ["_score", "indexed_at", "id"]


def test_build_bm25_pagination_offset():
    q_page_3 = build_bm25_search_query("test", page=3, size=20)
    assert q_page_3["from"] == 40
    assert q_page_3["size"] == 20


def test_build_suggestions_query():
    sugg_query = build_suggestions_query("pyt", size=5)
    assert sugg_query["size"] == 5
    assert sugg_query["_source"] == ["title"]
    assert "query" in sugg_query
