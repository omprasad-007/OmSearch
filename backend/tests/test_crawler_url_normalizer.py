from crawler.om_crawler.url_normalizer import URLNormalizer


def test_normalizer_relative_resolution():
    normalizer = URLNormalizer()
    base = "https://example.com/blog/article-1"
    resolved = normalizer.normalize("../about", base_url=base)
    assert resolved == "https://example.com/about"


def test_normalizer_strips_fragments():
    normalizer = URLNormalizer()
    assert normalizer.normalize("https://example.com/docs#installation") == "https://example.com/docs"


def test_normalizer_strips_tracking_params_preserves_content():
    normalizer = URLNormalizer()
    url = "https://example.com/search?page=2&utm_source=twitter&q=python&fbclid=123"
    norm = normalizer.normalize(url)
    assert norm == "https://example.com/search?page=2&q=python"


def test_normalizer_rejects_credentials():
    normalizer = URLNormalizer()
    assert normalizer.normalize("https://user:pass@example.com/login") is None


def test_normalizer_forbidden_extensions():
    normalizer = URLNormalizer()
    is_crawlable, _ = normalizer.is_crawlable("https://example.com/files/archive.zip")
    assert not is_crawlable
    is_pdf, _ = normalizer.is_crawlable("https://example.com/paper.pdf")
    assert not is_pdf


def test_normalizer_domain_allowlist():
    normalizer = URLNormalizer(allowed_domains=["example.com"])
    assert normalizer.is_crawlable("https://example.com/page")[0]
    assert normalizer.is_crawlable("https://sub.example.com/page")[0]
    assert not normalizer.is_crawlable("https://otherdomain.org/page")[0]


def test_normalizer_validate_canonical():
    normalizer = URLNormalizer(allowed_domains=["example.com"])
    curr = "https://example.com/article?page=1"
    
    # Valid canonical
    canon = normalizer.validate_canonical("https://example.com/article", curr)
    assert canon == "https://example.com/article"

    # Cross-domain canonical to unapproved domain rejected
    unapproved = normalizer.validate_canonical("https://malicious.org/fake", curr)
    assert unapproved is None
