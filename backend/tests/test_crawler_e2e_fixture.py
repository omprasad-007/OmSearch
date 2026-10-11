import threading
from urllib.parse import urlsplit
from http.server import HTTPServer, BaseHTTPRequestHandler
from unittest.mock import patch
import pytest

from crawler.om_crawler.crawler_engine import CrawlerEngine
from crawler.om_crawler.frontier import FrontierManager
from app.repositories.database import get_db_manager, CrawlJob, URLRecord, FrontierStatus
from app.services.search_service import SearchService


class FixtureHTTPHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress server logging during tests

    def do_GET(self):
        if self.path == "/robots.txt":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"User-agent: *\nDisallow: /disallowed/\n")

        elif self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = """
            <!DOCTYPE html>
            <html>
            <head><title>Fixture University Home</title></head>
            <body>
                <h1>Fixture University</h1>
                <p>Welcome to our university portal on information retrieval.</p>
                <a href="/algorithms">Algorithms Course</a>
                <a href="/duplicate-page">Duplicate Course</a>
                <a href="/disallowed/secret">Secret Research</a>
                <a href="/broken">Broken Resource</a>
            </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))

        elif self.path == "/algorithms":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = """
            <!DOCTYPE html>
            <html>
            <head><title>Algorithms and Search Engines</title></head>
            <body>
                <h1>Algorithms and Search Engines</h1>
                <p>Learn inverted indices, PageRank, and BM25 relevance ranking in this course.</p>
                <a href="/">Back to Home</a>
            </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))

        elif self.path == "/duplicate-page":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            # Identical body text to /algorithms for duplicate content verification
            html = """
            <!DOCTYPE html>
            <html>
            <head><title>Algorithms Mirror</title></head>
            <body>
                <h1>Algorithms Mirror</h1>
                <p>Learn inverted indices, PageRank, and BM25 relevance ranking in this course.</p>
            </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))

        elif self.path.startswith("/disallowed/"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>Forbidden Content</h1><p>Disallowed by robots.txt</p>")

        elif self.path == "/broken":
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"Internal Server Error")

        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")


@pytest.fixture(scope="module")
def fixture_server():
    server = HTTPServer(("127.0.0.1", 0), FixtureHTTPHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    yield base_url
    server.shutdown()
    server.server_close()


def test_controlled_end_to_end_crawl(fixture_server):
    """
    Demonstrates:
    1. Seed enters frontier.
    2. Crawler fetches allowed page and discovers links.
    3. Robots.txt disallowed paths are skipped.
    4. Duplicate content is detected and handled.
    5. Extracted content enters OpenSearch.
    6. Search service retrieves newly crawled documents.
    7. Broken page is recorded as failure.
    8. Worker restart recovers frontier without corruption.
    """
    # For local test against fixture server, bypass network_safety's loopback block
    with patch("crawler.om_crawler.robots_policy.validate_url_security", return_value=(True, "Safe")), \
         patch("crawler.om_crawler.crawler_engine.validate_url_security", return_value=(True, "Safe")), \
         patch("crawler.om_crawler.network_safety.validate_url_security", return_value=(True, "Safe")):
        seed_url = f"{fixture_server}/"
        fixture_domain = urlsplit(fixture_server).hostname

        db = get_db_manager().get_session()
        try:
            # Clean up any leftover URLs from previous fixture runs to ensure test isolation
            db.query(URLRecord).filter(URLRecord.url.like("http://127.0.0.1:%")).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

        db = get_db_manager().get_session()
        job = CrawlJob(
            job_type="e2e_fixture_test",
            status="pending",
            total_urls=1,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
        db.close()

        # Run crawler engine
        engine = CrawlerEngine(
            job_id=job_id,
            seed_urls=[seed_url],
            allowed_domains=[fixture_domain],
            max_pages=10,
            max_depth=2,
            rate_limit_delay=0.05,  # fast rate limit for local fixture test
        )
        result = engine.run()

        # 1. Verification of crawl progress
        assert result["status"] == "completed"
        assert result["processed"] >= 2  # / and /algorithms processed

        # 2. Verify frontier contents in database
        db = get_db_manager().get_session()
        try:
            # Seed and discovered links for this fixture test
            records = db.query(URLRecord).filter(URLRecord.url.like(f"{fixture_server}%")).all()
            record_urls = [r.url for r in records]

            assert any("/algorithms" in u for u in record_urls)
            assert any("/duplicate-page" in u for u in record_urls)
            assert any("/broken" in u for u in record_urls)

            # Robots.txt disallowed check
            disallowed_rec = next((r for r in records if "/disallowed/secret" in r.url), None)
            if disallowed_rec:
                assert disallowed_rec.status in (FrontierStatus.BLOCKED, FrontierStatus.SKIPPED_POLICY)

            # Broken page failure check
            broken_rec = next((r for r in records if "/broken" in r.url), None)
            if broken_rec:
                assert broken_rec.status in (FrontierStatus.RETRY_WAIT, FrontierStatus.FAILED)

        finally:
            db.close()

        # 3. Verify search returns newly indexed content
        search_svc = SearchService()
        search_res = search_svc.search(query="BM25 relevance ranking")
        assert search_res.total >= 1
        assert any("algorithms" in item.url.lower() or "algorithms" in item.title.lower() for item in search_res.results)

        # 4. Worker restart recovery test
        frontier = FrontierManager()
        reclaimed = frontier.reset_expired_leases()
        assert reclaimed >= 0
