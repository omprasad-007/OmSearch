import pytest
from pydantic import ValidationError
from app.schemas.search import SearchQueryRequest


def test_valid_query():
    req = SearchQueryRequest(q="distributed indexing", page=2, size=15)
    assert req.q == "distributed indexing"
    assert req.page == 2
    assert req.size == 15


def test_query_trims_whitespace():
    req = SearchQueryRequest(q="   python 3.12   ")
    assert req.q == "python 3.12"


def test_empty_query_rejected():
    with pytest.raises(ValidationError):
        SearchQueryRequest(q="   ")


def test_page_bounds():
    with pytest.raises(ValidationError):
        SearchQueryRequest(q="test", page=0)


def test_size_bounds():
    with pytest.raises(ValidationError):
        SearchQueryRequest(q="test", size=0)

    with pytest.raises(ValidationError):
        SearchQueryRequest(q="test", size=51)  # max is 50


def test_max_query_length():
    long_q = "a" * 201
    with pytest.raises(ValidationError):
        SearchQueryRequest(q=long_q)
