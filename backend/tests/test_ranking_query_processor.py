import pytest
from app.ranking.query_processor import QueryProcessor, ProcessedQuery


def test_query_processor_normalization_and_phrases():
    qp = QueryProcessor()
    res = qp.process('  "Python Programming"   Tutorial  ')

    assert res.normalized_query == 'python programming tutorial'
    assert res.quoted_phrases == ['Python Programming']
    assert 'python' in res.tokens
    assert 'tutorial' in res.tokens


def test_query_processor_intent_classification():
    qp = QueryProcessor()

    # Navigational
    res_nav = qp.process('python documentation official')
    assert res_nav.intent == 'navigational'

    # Technical
    res_tech = qp.process('def process_data api error')
    assert res_tech.intent == 'technical'
    assert res_tech.has_technical_identifiers is True

    # Freshness
    res_fresh = qp.process('fastapi latest release 2024')
    assert res_fresh.intent == 'freshness'

    # Informational
    res_info = qp.process('what is inverted index tutorial')
    assert res_info.intent == 'informational'


def test_query_processor_technical_identifier_preservation():
    qp = QueryProcessor()
    res = qp.process('import asyncio script.py')

    assert res.has_technical_identifiers is True
    assert 'script.py' in res.tokens


def test_query_processor_spelling_suggestion():
    qp = QueryProcessor(vocabulary={'python', 'database', 'search'})

    # Typo: 'pythn' -> 'python'
    res = qp.process('pythn engine')
    assert res.spelling_suggestion == 'python engine'

    # Already correct -> None
    res_correct = qp.process('python database')
    assert res_correct.spelling_suggestion is None


def test_query_processor_empty_query():
    qp = QueryProcessor()
    res = qp.process('   ')

    assert res.normalized_query == ''
    assert res.tokens == []
    assert res.intent == 'general'
