"""
OM Search - 10,000 Document High-Throughput Web Indexer
Fetches and indexes 10,000 real-world encyclopedia articles and technical topics
using concurrent batched Wikimedia API pipelines, instant SQLite lifecycle logging,
batch fallback store persistence, and PageRank link authority recomputation.
"""
import sys
import time
import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Set, Optional
from urllib.parse import urlparse
import concurrent.futures
import httpx

# Ensure backend and root are in sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "backend"))
sys.path.insert(0, str(root_dir))

from app.core.logging import setup_logging
from app.schemas.document import DocumentModel
from app.repositories.opensearch_repo import get_opensearch_repo
from app.repositories.database import get_db_manager, URLRecord, DocumentLifecycle
from app.ingestion.normalizer import compute_url_id, generate_snippet
from crawler.om_crawler.link_graph import LinkGraphManager

setup_logging(level="INFO")
logger = logging.getLogger("om_indexer.10k")

USER_AGENT = "OMSearchEngine/3.0 (https://github.com/om-search; contact: crawler@omsearch.local)"

CATEGORIES = [
    "Computer_science", "Artificial_intelligence", "Software_engineering", "Programming_languages",
    "Physics", "Quantum_mechanics", "Astronomy", "Solar_System",
    "Chemistry", "Materials_science", "Nanotechnology",
    "Biology", "Genetics", "Neuroscience", "Medicine",
    "Mathematics", "Statistics", "Calculus", "Linear_algebra",
    "World_history", "Ancient_civilizations", "Renaissance", "Industrial_Revolution",
    "Geography", "Countries", "Oceans", "Mountain_ranges",
    "Philosophy", "Ethics", "Epistemology", "Literature", "Architecture",
    "Economics", "Renewable_energy", "Robotics", "Telecommunications",
]


class Massive10KIndexer:
    def __init__(self, target_docs: int = 10000, workers: int = 6):
        self.target_docs = target_docs
        self.workers = workers
        self.os_repo = get_opensearch_repo()
        self.db_mgr = get_db_manager()
        self.link_graph = LinkGraphManager()
        
        self.indexed_count = 0
        self.visited_urls: Set[str] = set()

        # Load already indexed URLs to prevent duplication
        store_path = root_dir / "om_fallback_store.json"
        if store_path.exists():
            try:
                with open(store_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data.values():
                        if "url" in item:
                            self.visited_urls.add(item["url"])
                        if "canonical_url" in item:
                            self.visited_urls.add(item["canonical_url"])
                print(f"Loaded {len(self.visited_urls)} previously indexed URLs.")
            except Exception as e:
                logger.warning("Could not read existing store: %s", e)

    def fetch_batch_random(self, client: httpx.Client, limit: int = 50) -> List[Dict[str, Any]]:
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "format": "json",
            "generator": "random",
            "grnnamespace": "0",
            "grnlimit": min(limit, 50),
            "prop": "extracts|info|links",
            "inprop": "url",
            "explaintext": "1",
            "exintro": "0",
            "pllimit": "20",
        }
        try:
            resp = client.get(url, params=params, timeout=12.0)
            if resp.status_code == 200:
                data = resp.json()
                pages = data.get("query", {}).get("pages", {})
                return list(pages.values())
        except Exception as e:
            logger.debug("Random batch fetch notice: %s", e)
        return []

    def fetch_batch_category(self, client: httpx.Client, category: str, limit: int = 50) -> List[Dict[str, Any]]:
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "format": "json",
            "generator": "categorymembers",
            "gcmtitle": f"Category:{category}",
            "gcmnamespace": "0",
            "gcmlimit": min(limit, 50),
            "prop": "extracts|info|links",
            "inprop": "url",
            "explaintext": "1",
            "exintro": "0",
            "pllimit": "20",
        }
        try:
            resp = client.get(url, params=params, timeout=12.0)
            if resp.status_code == 200:
                data = resp.json()
                pages = data.get("query", {}).get("pages", {})
                return list(pages.values())
        except Exception as e:
            logger.debug("Category %s fetch notice: %s", category, e)
        return []

    def index_pages_batch(self, pages: List[Dict[str, Any]]) -> int:
        if not pages:
            return 0

        now = datetime.now(timezone.utc)
        db = self.db_mgr.get_session()
        docs_to_index: List[DocumentModel] = []
        links_to_record: List[tuple] = []
        added_count = 0

        try:
            for page in pages:
                if self.indexed_count >= self.target_docs:
                    break

                raw_url = page.get("canonicalurl") or page.get("fullurl")
                if not raw_url or raw_url in self.visited_urls:
                    continue

                title = page.get("title", "").strip()
                content = page.get("extract", "").strip()
                if not title or len(content.split()) < 30:
                    continue

                self.visited_urls.add(raw_url)
                doc_id = compute_url_id(raw_url)
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                domain = urlparse(raw_url).hostname or "en.wikipedia.org"
                snippet = generate_snippet(content, max_length=260)

                doc_model = DocumentModel(
                    id=doc_id,
                    url=raw_url,
                    canonical_url=raw_url,
                    domain=domain,
                    title=title,
                    content=content,
                    snippet=snippet,
                    language="en",
                    published_at=None,
                    fetched_at=now,
                    indexed_at=now,
                    content_hash=content_hash,
                    http_status=200,
                    document_type="encyclopedia",
                )
                docs_to_index.append(doc_model)

                # Collect outgoing links
                raw_links = page.get("links", [])
                out_urls = []
                for l in raw_links:
                    ltitle = l.get("title", "")
                    if ltitle:
                        out_u = f"https://en.wikipedia.org/wiki/{ltitle.replace(' ', '_')}"
                        out_urls.append(out_u)
                if out_urls:
                    links_to_record.append((raw_url, out_urls))

                # SQLite lifecycle entry
                db.add(
                    URLRecord(
                        url=raw_url,
                        canonical_url=raw_url,
                        domain=domain,
                        http_status=200,
                        content_hash=content_hash,
                        last_fetched_at=now,
                        indexed_at=now,
                    )
                )
                db.add(
                    DocumentLifecycle(
                        canonical_url=raw_url,
                        action="indexed",
                        status="success",
                        details=json.dumps({"title": title, "length": len(content)}),
                    )
                )
                added_count += 1
                self.indexed_count += 1

            if docs_to_index:
                # Batch persist into OpenSearch repository / fallback store
                self.os_repo.index_documents_bulk(docs_to_index)
                db.commit()

            # Record links into link graph in a single bulk transaction
            if links_to_record:
                try:
                    self.link_graph.record_batch_links(links_to_record)
                except Exception:
                    pass

        except Exception as e:
            db.rollback()
            logger.error("Batch commit error: %s", e)
        finally:
            db.close()

        return added_count

    def run(self):
        print(f"\n=======================================================")
        print(f"⚡ OM SEARCH MASSIVE 10,000-DOCUMENT PIPELINE")
        print(f"Target count: {self.target_docs:,} pages")
        print(f"Concurrency:  {self.workers} workers")
        print(f"=======================================================\n")

        start_time = time.time()
        last_logged = 0
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }

        with httpx.Client(timeout=15.0, headers=headers) as client:
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as executor:
                # 1. First sweep through curated topic categories
                cat_futures = [
                    executor.submit(self.fetch_batch_category, client, cat, 50)
                    for cat in CATEGORIES
                ]
                for f in concurrent.futures.as_completed(cat_futures):
                    pages = f.result()
                    newly = self.index_pages_batch(pages)
                    if newly > 0 and (self.indexed_count - last_logged >= 250 or self.indexed_count >= self.target_docs):
                        print(f"[{self.indexed_count:,} / {self.target_docs:,}] 📚 ({((self.indexed_count/self.target_docs)*100):.1f}%) Indexed category batch. Total indexed: {self.indexed_count:,}")
                        last_logged = self.indexed_count
                    if self.indexed_count >= self.target_docs:
                        break

                # 2. Complete remaining quota via random generator batches
                while self.indexed_count < self.target_docs:
                    remaining = self.target_docs - self.indexed_count
                    batch_size = min(50, remaining)
                    num_tasks = min(self.workers * 2, (remaining // batch_size) + 1)
                    
                    random_futures = [
                        executor.submit(self.fetch_batch_random, client, batch_size)
                        for _ in range(num_tasks)
                    ]
                    for f in concurrent.futures.as_completed(random_futures):
                        pages = f.result()
                        newly = self.index_pages_batch(pages)
                        if newly > 0 and (self.indexed_count - last_logged >= 250 or self.indexed_count >= self.target_docs):
                            elapsed = round(time.time() - start_time, 1)
                            rate = round(self.indexed_count / max(elapsed, 0.1), 1)
                            print(f"[{self.indexed_count:,} / {self.target_docs:,}] 🚀 ({((self.indexed_count/self.target_docs)*100):.1f}%) Indexed: {self.indexed_count:,} docs | Rate: {rate} docs/s")
                            last_logged = self.indexed_count
                        if self.indexed_count >= self.target_docs:
                            break

        # Flush repository to disk
        self.os_repo.flush_fallback_store()
        total_time = round(time.time() - start_time, 2)

        print(f"\n=======================================================")
        print(f"🎉 10,000-PAGE INDEXING COMPLETE in {total_time}s!")
        print(f"Total newly indexed in this run: {self.indexed_count}")
        print(f"Throughput: {round(self.indexed_count / max(total_time, 0.1), 1)} docs/sec")
        print(f"Recomputing link graph and PageRank...")

        try:
            pr_res = self.link_graph.compute_and_save_authority(damping=0.85)
            print(f"PageRank authority successfully updated ({pr_res.get('nodes_count', 0)} nodes evaluated).")
        except Exception as e:
            logger.warning("PageRank notice: %s", e)

        print(f"=======================================================\n")


def main():
    target = 10000
    if len(sys.argv) > 1:
        try:
            target = int(sys.argv[1])
        except ValueError:
            pass

    indexer = Massive10KIndexer(target_docs=target, workers=6)
    indexer.run()


if __name__ == "__main__":
    main()
