"""
OM Search - High-Throughput Real Web Crawler
Crawls a diverse, multi-category set of high-value web seeds with concurrent fetching,
immediate indexing, and PageRank link authority updates.
"""
import sys
import time
import logging
from pathlib import Path
from typing import List, Dict, Any, Set, Optional
from urllib.parse import urlparse
import concurrent.futures
import httpx

# Ensure backend and project root are in sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "backend"))
sys.path.insert(0, str(root_dir))

from app.core.logging import setup_logging
from app.repositories.database import get_db_manager
from crawler.om_crawler.network_safety import validate_url_security, is_allowed_content_type, MAX_RESPONSE_BYTES
from crawler.om_crawler.url_normalizer import URLNormalizer
from crawler.om_crawler.robots_policy import RobotsPolicyManager, DEFAULT_USER_AGENT
from crawler.om_crawler.extractor import HTMLExtractor
from crawler.om_crawler.indexing_pipeline import CrawlerIndexingService
from crawler.om_crawler.link_graph import LinkGraphManager

setup_logging(level="INFO")
logger = logging.getLogger("om_crawler.massive")

# Comprehensive high-authority real-web seeds across diverse topics
CURATED_SEEDS = [
    # 1. Computer Science, AI & Cybernetics
    "https://en.wikipedia.org/wiki/Artificial_intelligence",
    "https://en.wikipedia.org/wiki/Machine_learning",
    "https://en.wikipedia.org/wiki/Deep_learning",
    "https://en.wikipedia.org/wiki/Computer_science",
    "https://en.wikipedia.org/wiki/Algorithm",
    "https://en.wikipedia.org/wiki/Search_engine",
    "https://en.wikipedia.org/wiki/World_Wide_Web",
    "https://en.wikipedia.org/wiki/Internet",
    "https://en.wikipedia.org/wiki/Operating_system",
    "https://en.wikipedia.org/wiki/Linux",
    "https://en.wikipedia.org/wiki/Cloud_computing",
    "https://en.wikipedia.org/wiki/Compiler",
    "https://en.wikipedia.org/wiki/Database",
    "https://en.wikipedia.org/wiki/Distributed_computing",
    "https://en.wikipedia.org/wiki/Cryptography",
    "https://en.wikipedia.org/wiki/Blockchain",
    "https://en.wikipedia.org/wiki/Artificial_neural_network",
    "https://en.wikipedia.org/wiki/Natural_language_processing",
    "https://en.wikipedia.org/wiki/Computer_vision",
    "https://en.wikipedia.org/wiki/Turing_machine",
    "https://en.wikipedia.org/wiki/Cybersecurity",
    "https://en.wikipedia.org/wiki/Functional_programming",
    "https://en.wikipedia.org/wiki/Object-oriented_programming",
    "https://en.wikipedia.org/wiki/Information_retrieval",
    "https://en.wikipedia.org/wiki/Data_structure",
    "https://en.wikipedia.org/wiki/Graph_theory",
    "https://en.wikipedia.org/wiki/Relational_database",
    "https://en.wikipedia.org/wiki/Software_engineering",
    "https://en.wikipedia.org/wiki/Quantum_computing",
    "https://en.wikipedia.org/wiki/Computer_network",
    "https://en.wikipedia.org/wiki/Microprocessor",
    "https://en.wikipedia.org/wiki/Semiconductor",

    # 2. Programming Languages & Developer Documentation
    "https://en.wikipedia.org/wiki/Python_(programming_language)",
    "https://en.wikipedia.org/wiki/JavaScript",
    "https://en.wikipedia.org/wiki/Rust_(programming_language)",
    "https://en.wikipedia.org/wiki/C_(programming_language)",
    "https://en.wikipedia.org/wiki/C%2B%2B",
    "https://en.wikipedia.org/wiki/Java_(programming_language)",
    "https://en.wikipedia.org/wiki/Go_(programming_language)",
    "https://en.wikipedia.org/wiki/TypeScript",
    "https://en.wikipedia.org/wiki/HTML",
    "https://en.wikipedia.org/wiki/CSS",
    "https://docs.python.org/3/tutorial/index.html",
    "https://docs.python.org/3/library/functions.html",
    "https://docs.python.org/3/library/stdtypes.html",
    "https://fastapi.tiangolo.com/",
    "https://react.dev/",
    "https://www.postgresql.org/docs/current/intro-whatis.html",
    "https://www.sqlite.org/about.html",
    "https://developer.mozilla.org/en-US/docs/Web/HTTP/Overview",
    "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide",

    # 3. Physics & Astronomy
    "https://en.wikipedia.org/wiki/Physics",
    "https://en.wikipedia.org/wiki/Quantum_mechanics",
    "https://en.wikipedia.org/wiki/General_relativity",
    "https://en.wikipedia.org/wiki/Special_relativity",
    "https://en.wikipedia.org/wiki/Thermodynamics",
    "https://en.wikipedia.org/wiki/Particle_physics",
    "https://en.wikipedia.org/wiki/Gravitation",
    "https://en.wikipedia.org/wiki/Big_Bang",
    "https://en.wikipedia.org/wiki/Black_hole",
    "https://en.wikipedia.org/wiki/Speed_of_light",
    "https://en.wikipedia.org/wiki/Higgs_boson",
    "https://en.wikipedia.org/wiki/Superconductivity",
    "https://en.wikipedia.org/wiki/Electromagnetism",
    "https://en.wikipedia.org/wiki/Nuclear_fusion",
    "https://en.wikipedia.org/wiki/Nuclear_fission",
    "https://en.wikipedia.org/wiki/Astronomy",
    "https://en.wikipedia.org/wiki/Milky_Way",
    "https://en.wikipedia.org/wiki/Andromeda_Galaxy",
    "https://en.wikipedia.org/wiki/Solar_System",
    "https://en.wikipedia.org/wiki/Sun",
    "https://en.wikipedia.org/wiki/Earth",
    "https://en.wikipedia.org/wiki/Moon",
    "https://en.wikipedia.org/wiki/Mars",
    "https://en.wikipedia.org/wiki/Jupiter",
    "https://en.wikipedia.org/wiki/Saturn",
    "https://en.wikipedia.org/wiki/Space_exploration",
    "https://en.wikipedia.org/wiki/Hubble_Space_Telescope",
    "https://en.wikipedia.org/wiki/James_Webb_Space_Telescope",
    "https://en.wikipedia.org/wiki/Apollo_11",
    "https://en.wikipedia.org/wiki/International_Space_Station",
    "https://en.wikipedia.org/wiki/Exoplanet",
    "https://en.wikipedia.org/wiki/Supernova",

    # 4. Chemistry & Materials Science
    "https://en.wikipedia.org/wiki/Chemistry",
    "https://en.wikipedia.org/wiki/Periodic_table",
    "https://en.wikipedia.org/wiki/Chemical_element",
    "https://en.wikipedia.org/wiki/Organic_chemistry",
    "https://en.wikipedia.org/wiki/Molecule",
    "https://en.wikipedia.org/wiki/Atom",
    "https://en.wikipedia.org/wiki/Water",
    "https://en.wikipedia.org/wiki/Polymer",
    "https://en.wikipedia.org/wiki/Catalysis",
    "https://en.wikipedia.org/wiki/Nanotechnology",
    "https://en.wikipedia.org/wiki/Graphene",
    "https://en.wikipedia.org/wiki/Biochemistry",

    # 5. Biology, Genetics & Medicine
    "https://en.wikipedia.org/wiki/Biology",
    "https://en.wikipedia.org/wiki/Evolution",
    "https://en.wikipedia.org/wiki/Genetics",
    "https://en.wikipedia.org/wiki/DNA",
    "https://en.wikipedia.org/wiki/CRISPR",
    "https://en.wikipedia.org/wiki/Human_brain",
    "https://en.wikipedia.org/wiki/Immune_system",
    "https://en.wikipedia.org/wiki/Virus",
    "https://en.wikipedia.org/wiki/Bacteria",
    "https://en.wikipedia.org/wiki/Photosynthesis",
    "https://en.wikipedia.org/wiki/Neuroscience",
    "https://en.wikipedia.org/wiki/Cell_(biology)",
    "https://en.wikipedia.org/wiki/Vaccine",
    "https://en.wikipedia.org/wiki/Antibiotic",
    "https://en.wikipedia.org/wiki/Physiology",
    "https://en.wikipedia.org/wiki/Ecology",
    "https://en.wikipedia.org/wiki/Biodiversity",

    # 6. Mathematics & Logic
    "https://en.wikipedia.org/wiki/Mathematics",
    "https://en.wikipedia.org/wiki/Calculus",
    "https://en.wikipedia.org/wiki/Linear_algebra",
    "https://en.wikipedia.org/wiki/Probability_theory",
    "https://en.wikipedia.org/wiki/Statistics",
    "https://en.wikipedia.org/wiki/Prime_number",
    "https://en.wikipedia.org/wiki/Number_theory",
    "https://en.wikipedia.org/wiki/Geometry",
    "https://en.wikipedia.org/wiki/Trigonometry",
    "https://en.wikipedia.org/wiki/Mathematical_logic",
    "https://en.wikipedia.org/wiki/Game_theory",
    "https://en.wikipedia.org/wiki/Chaos_theory",
    "https://en.wikipedia.org/wiki/Combinatorics",

    # 7. World History & Civilizations
    "https://en.wikipedia.org/wiki/History",
    "https://en.wikipedia.org/wiki/Ancient_Egypt",
    "https://en.wikipedia.org/wiki/Ancient_Greece",
    "https://en.wikipedia.org/wiki/Roman_Empire",
    "https://en.wikipedia.org/wiki/Silk_Road",
    "https://en.wikipedia.org/wiki/Middle_Ages",
    "https://en.wikipedia.org/wiki/Renaissance",
    "https://en.wikipedia.org/wiki/Age_of_Discovery",
    "https://en.wikipedia.org/wiki/Industrial_Revolution",
    "https://en.wikipedia.org/wiki/French_Revolution",
    "https://en.wikipedia.org/wiki/World_War_I",
    "https://en.wikipedia.org/wiki/World_War_II",
    "https://en.wikipedia.org/wiki/Cold_War",
    "https://en.wikipedia.org/wiki/Byzantine_Empire",
    "https://en.wikipedia.org/wiki/Ottoman_Empire",
    "https://en.wikipedia.org/wiki/Ming_dynasty",
    "https://en.wikipedia.org/wiki/Indus_Valley_Civilisation",
    "https://en.wikipedia.org/wiki/Mughal_Empire",
    "https://en.wikipedia.org/wiki/British_Empire",
    "https://en.wikipedia.org/wiki/Russian_Empire",

    # 8. Geography, Places & Earth
    "https://en.wikipedia.org/wiki/India",
    "https://en.wikipedia.org/wiki/United_States",
    "https://en.wikipedia.org/wiki/Japan",
    "https://en.wikipedia.org/wiki/United_Kingdom",
    "https://en.wikipedia.org/wiki/Germany",
    "https://en.wikipedia.org/wiki/France",
    "https://en.wikipedia.org/wiki/Canada",
    "https://en.wikipedia.org/wiki/Australia",
    "https://en.wikipedia.org/wiki/Brazil",
    "https://en.wikipedia.org/wiki/South_Africa",
    "https://en.wikipedia.org/wiki/China",
    "https://en.wikipedia.org/wiki/Egypt",
    "https://en.wikipedia.org/wiki/Mount_Everest",
    "https://en.wikipedia.org/wiki/Amazon_rainforest",
    "https://en.wikipedia.org/wiki/Pacific_Ocean",
    "https://en.wikipedia.org/wiki/Atlantic_Ocean",
    "https://en.wikipedia.org/wiki/Sahara",
    "https://en.wikipedia.org/wiki/Antarctica",
    "https://en.wikipedia.org/wiki/Nile",
    "https://en.wikipedia.org/wiki/Grand_Canyon",
    "https://en.wikipedia.org/wiki/Great_Barrier_Reef",
    "https://en.wikipedia.org/wiki/Himalayas",
    "https://en.wikipedia.org/wiki/Alps",

    # 9. Arts, Literature, Philosophy & Architecture
    "https://en.wikipedia.org/wiki/Philosophy",
    "https://en.wikipedia.org/wiki/Plato",
    "https://en.wikipedia.org/wiki/Aristotle",
    "https://en.wikipedia.org/wiki/Epistemology",
    "https://en.wikipedia.org/wiki/Ethics",
    "https://en.wikipedia.org/wiki/William_Shakespeare",
    "https://en.wikipedia.org/wiki/Leonardo_da_Vinci",
    "https://en.wikipedia.org/wiki/Michelangelo",
    "https://en.wikipedia.org/wiki/Architecture",
    "https://en.wikipedia.org/wiki/Photography",
    "https://en.wikipedia.org/wiki/Symphony",
    "https://en.wikipedia.org/wiki/World_Heritage_Site",
    "https://en.wikipedia.org/wiki/Impressionism",
    "https://en.wikipedia.org/wiki/Nobel_Prize",
    "https://en.wikipedia.org/wiki/Library_of_Alexandria",
    "https://en.wikipedia.org/wiki/Literature",
    "https://en.wikipedia.org/wiki/Poetry",

    # 10. Economics, Governance & Renewable Energy
    "https://en.wikipedia.org/wiki/Economics",
    "https://en.wikipedia.org/wiki/Supply_and_demand",
    "https://en.wikipedia.org/wiki/Inflation",
    "https://en.wikipedia.org/wiki/Gross_domestic_product",
    "https://en.wikipedia.org/wiki/Stock_exchange",
    "https://en.wikipedia.org/wiki/Central_bank",
    "https://en.wikipedia.org/wiki/Globalization",
    "https://en.wikipedia.org/wiki/United_Nations",
    "https://en.wikipedia.org/wiki/Human_rights",
    "https://en.wikipedia.org/wiki/Democracy",
    "https://en.wikipedia.org/wiki/Renewable_energy",
    "https://en.wikipedia.org/wiki/Solar_power",
    "https://en.wikipedia.org/wiki/Wind_power",
    "https://en.wikipedia.org/wiki/Nuclear_power",
    "https://en.wikipedia.org/wiki/Electric_vehicle",
    "https://en.wikipedia.org/wiki/Robotics",

    # 11. Sports, Games & Recreation
    "https://en.wikipedia.org/wiki/Cricket",
    "https://en.wikipedia.org/wiki/Association_football",
    "https://en.wikipedia.org/wiki/Olympic_Games",
    "https://en.wikipedia.org/wiki/Basketball",
    "https://en.wikipedia.org/wiki/Tennis",
    "https://en.wikipedia.org/wiki/FIFA_World_Cup",
    "https://en.wikipedia.org/wiki/Tour_de_France",
    "https://en.wikipedia.org/wiki/Formula_One",
    "https://en.wikipedia.org/wiki/Chess",
    "https://en.wikipedia.org/wiki/Marathon",
    "https://en.wikipedia.org/wiki/Swimming_(sport)",
    "https://en.wikipedia.org/wiki/Badminton",
    "https://en.wikipedia.org/wiki/Athletics_(sport)",
    "https://en.wikipedia.org/wiki/Cinema",
    "https://en.wikipedia.org/wiki/Music",
]


class HighThroughputCrawler:
    def __init__(self, max_pages: int = 200, workers: int = 8):
        self.max_pages = max_pages
        self.workers = workers
        self.normalizer = URLNormalizer()
        self.robots_mgr = RobotsPolicyManager(default_delay=0.6)
        self.extractor = HTMLExtractor(normalizer=self.normalizer)
        self.indexer = CrawlerIndexingService()
        self.link_graph = LinkGraphManager()
        
        self.visited_urls: Set[str] = set()
        
        # Load already-indexed URLs so that this run indexes 200 DIFFERENT, NEW pages!
        store_path = root_dir / "om_fallback_store.json"
        if store_path.exists():
            try:
                import json
                with open(store_path, "r", encoding="utf-8") as f:
                    store_data = json.load(f)
                    for item in store_data.values():
                        if "url" in item:
                            self.visited_urls.add(item["url"])
                        if "canonical_url" in item:
                            self.visited_urls.add(item["canonical_url"])
                print(f"Loaded {len(self.visited_urls)} previously indexed URLs to avoid duplicates.")
            except Exception as e:
                logger.warning("Could not read fallback store: %s", e)

        # Initialize queue with seeds that haven't been visited yet
        self.queue: List[str] = [u for u in CURATED_SEEDS if u not in self.visited_urls]
        self.indexed_count = 0
        self.failed_count = 0

    def crawl(self) -> Dict[str, Any]:
        print(f"\n=======================================================")
        print(f"🚀 OM SEARCH MASSIVE WEB CRAWLER INITIATED")
        print(f"Seeds in queue:  {len(self.queue)} diverse, unvisited URLs")
        print(f"Target NEW docs: {self.max_pages} DIFFERENT pages")
        print(f"Workers:         {self.workers} concurrent threads")
        print(f"=======================================================\n")

        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }

        start_time = time.time()

        with httpx.Client(timeout=10.0, follow_redirects=True, headers=headers) as client:
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as executor:
                while (self.queue or self.indexed_count < self.max_pages) and self.indexed_count < self.max_pages:
                    # Pick a batch of URLs from queue
                    batch_urls = []
                    while self.queue and len(batch_urls) < self.workers * 2:
                        u = self.queue.pop(0)
                        if u not in self.visited_urls:
                            self.visited_urls.add(u)
                            batch_urls.append(u)

                    if not batch_urls:
                        print("Queue empty, waiting briefly for outgoing link expansion...")
                        break

                    # Map batch to executor
                    future_to_url = {
                        executor.submit(self._fetch_and_index, u, client): u
                        for u in batch_urls
                    }

                    for future in concurrent.futures.as_completed(future_to_url):
                        target_u = future_to_url[future]
                        try:
                            res = future.result()
                            if res and res.get("indexed"):
                                self.indexed_count += 1
                                print(f"[{self.indexed_count}/{self.max_pages}] ✅ INDEXED: {res.get('title', '')[:50]} ({target_u})")
                                # Add discovered outgoing links
                                for link in res.get("links", []):
                                    if link not in self.visited_urls and len(self.queue) < 3000:
                                        # Filter for high-signal encyclopedia and doc pages
                                        if any(ns in link for ns in [":Talk", ":Help", ":Category", ":Special", ":File", ":Portal", ":Template", ":Wikipedia:"]):
                                            continue
                                        self.queue.append(link)
                            elif res and res.get("status") == "duplicate":
                                print(f"[--] ℹ️ DUPLICATE: {target_u}")
                            else:
                                self.failed_count += 1
                        except Exception as e:
                            self.failed_count += 1
                            logger.debug("Fetch error for %s: %s", target_u, e)

                        if self.indexed_count >= self.max_pages:
                            break

        total_time = round(time.time() - start_time, 2)
        print(f"\n=======================================================")
        print(f"🎉 CRAWL FINISHED in {total_time}s")
        print(f"Successfully Indexed: {self.indexed_count} pages")
        print(f"Failed / Skipped:     {self.failed_count} pages")
        print(f"Updating Link Graph and PageRank Authority...")
        
        # Compute and persist updated PageRank authority
        try:
            pr_res = self.link_graph.compute_and_save_authority(damping=0.85)
            print("PageRank updated successfully.")
        except Exception as e:
            logger.warning("PageRank update notice: %s", e)

        print(f"=======================================================\n")
        return {"indexed": self.indexed_count, "time_sec": total_time}

    def _fetch_and_index(self, url: str, client: httpx.Client) -> Optional[Dict[str, Any]]:
        # 1. Network security
        safe, reason = validate_url_security(url, check_dns=True)
        if not safe:
            return None

        # 2. Robots check
        allowed, _ = self.robots_mgr.is_allowed(url)
        if not allowed:
            return None

        # 3. Fetch
        domain = urlparse(url).hostname or ""
        self.robots_mgr.record_host_access(domain)
        resp = client.get(url)
        if resp.status_code != 200:
            return None

        content_type = resp.headers.get("content-type", "")
        if not is_allowed_content_type(content_type):
            return None

        if len(resp.content) > 6 * 1024 * 1024:
            return None

        final_url = str(resp.url)

        # 4. Extract
        extracted = self.extractor.extract(
            html_content=resp.text,
            url=url,
            final_url=final_url,
            http_status=resp.status_code,
            content_type=content_type,
        )

        if not extracted.title or not extracted.main_text or len(extracted.main_text.split()) < 15:
            return None

        # 5. Index immediately
        index_res = self.indexer.process_and_index(extracted)

        # 6. Record links
        if extracted.outgoing_links:
            self.link_graph.record_page_links(source_url=final_url, outgoing_links=extracted.outgoing_links)

        return {
            "indexed": index_res.get("indexed", False),
            "status": index_res.get("status"),
            "title": extracted.title,
            "url": final_url,
            "links": extracted.outgoing_links[:20] if extracted.outgoing_links else [],
        }


def main():
    max_pages = 200
    workers = 8
    if len(sys.argv) > 1:
        try:
            max_pages = int(sys.argv[1])
        except ValueError:
            pass

    crawler = HighThroughputCrawler(max_pages=max_pages, workers=workers)
    crawler.crawl()


if __name__ == "__main__":
    main()
