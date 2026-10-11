from crawler.om_crawler.extractor import HTMLExtractor


def test_html_extractor_basic():
    extractor = HTMLExtractor()
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <title>Search Engine Architecture</title>
        <meta name="description" content="An in-depth article on web search engines.">
        <link rel="canonical" href="https://example.com/search-architecture">
    </head>
    <body>
        <nav><a href="/home">Home</a></nav>
        <article>
            <h1>Search Engine Architecture</h1>
            <p>Modern web search engines use inverted indices, BM25 scoring, and crawling frontiers.</p>
            <p>Read more in our <a href="/distributed-systems">distributed systems guide</a>.</p>
        </article>
        <footer><p>Copyright 2026</p></footer>
    </body>
    </html>
    """

    doc = extractor.extract(html, url="https://example.com/search-architecture?utm_source=twitter")

    assert doc.title == "Search Engine Architecture"
    assert doc.meta_description == "An in-depth article on web search engines."
    assert "inverted indices" in doc.main_text
    assert doc.canonical_url == "https://example.com/search-architecture"
    assert doc.language == "en"
    assert "https://example.com/distributed-systems" in doc.outgoing_links
    assert len(doc.content_hash) == 64


def test_html_extractor_handles_empty_html():
    extractor = HTMLExtractor()
    doc = extractor.extract("", url="https://example.com/empty")
    assert doc.title == ""
    assert doc.main_text == ""
    assert doc.outgoing_links == []
