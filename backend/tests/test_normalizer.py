import pytest
from app.ingestion.normalizer import (
    normalize_url,
    extract_domain,
    compute_url_id,
    compute_content_hash,
    generate_snippet,
)


def test_normalize_url_basic():
    url = "HTTP://Example.COM:80/path/to/page/?utm_source=twitter&b=2&a=1#section"
    normalized = normalize_url(url)
    assert normalized == "http://example.com/path/to/page?a=1&b=2"


def test_normalize_url_https_port():
    url = "https://example.com:443/docs/"
    normalized = normalize_url(url)
    assert normalized == "https://example.com/docs"


def test_normalize_url_strips_tracking_params():
    url = "https://example.com/article?utm_medium=email&utm_campaign=winter&id=123&fbclid=abc"
    normalized = normalize_url(url)
    assert normalized == "https://example.com/article?id=123"


def test_normalize_url_root_path():
    url = "https://example.com/"
    normalized = normalize_url(url)
    assert normalized == "https://example.com/"


def test_extract_domain():
    assert extract_domain("https://sub.example.com/path?a=1") == "sub.example.com"
    assert extract_domain("http://example.org:8080/hello") == "example.org"


def test_compute_url_id_deterministic():
    id1 = compute_url_id("https://example.com/page1")
    id2 = compute_url_id("https://example.com/page1")
    id3 = compute_url_id("https://example.com/page2")
    assert id1 == id2
    assert id1 != id3
    assert len(id1) == 24


def test_compute_content_hash_whitespace_insensitive():
    text1 = "This is a   sample document with   spaces."
    text2 = "this is a sample document with spaces."
    assert compute_content_hash(text1) == compute_content_hash(text2)


def test_generate_snippet():
    long_text = "Word " * 100
    snippet = generate_snippet(long_text, max_length=50)
    assert len(snippet) <= 55
    assert snippet.endswith("...")
