import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Set, Tuple, Optional
from urllib.parse import urlparse

from app.repositories.database import get_db_manager, PageLink, PageAuthority, URLRecord
from crawler.om_crawler.pagerank import PageRankCalculator
from crawler.om_crawler.url_normalizer import URLNormalizer

logger = logging.getLogger(__name__)


class LinkGraphManager:
    """
    Manages directed hyperlink graph persistence and offline authority computation.
    """

    def __init__(self, normalizer: Optional[URLNormalizer] = None):
        self.db_mgr = get_db_manager()
        self.normalizer = normalizer or URLNormalizer()
        self.calculator = PageRankCalculator()

    def record_page_links(
        self,
        source_url: str,
        outgoing_links: List[str],
        anchor_texts: Optional[Dict[str, str]] = None,
    ) -> int:
        """
        Record outgoing links discovered during crawl into the page_links table.
        """
        if not outgoing_links:
            return 0

        anchors = anchor_texts or {}
        norm_src = self.normalizer.normalize(source_url)
        if not norm_src:
            return 0

        src_domain = urlparse(norm_src).hostname or ""
        db = self.db_mgr.get_session()
        links_added = 0

        try:
            seen_targets: Set[str] = set()
            for raw_tgt in outgoing_links:
                norm_tgt = self.normalizer.normalize(raw_tgt, base_url=norm_src)
                if not norm_tgt or norm_tgt == norm_src or norm_tgt in seen_targets:
                    continue  # Skip self-links and duplicate targets within page

                seen_targets.add(norm_tgt)
                tgt_domain = urlparse(norm_tgt).hostname or ""
                anchor = anchors.get(raw_tgt, "")

                edge = PageLink(
                    source_url=norm_src,
                    target_url=norm_tgt,
                    source_domain=src_domain,
                    target_domain=tgt_domain,
                    anchor_text=anchor[:255] if anchor else None,
                )
                db.add(edge)
                links_added += 1

            db.commit()
            return links_added
        except Exception as e:
            db.rollback()
            logger.error("Failed recording links for %s: %s", source_url, e)
            return 0
        finally:
            db.close()

    def record_batch_links(self, batch_links: List[Tuple[str, List[str]]]) -> int:
        """Batch record directed links across multiple pages in a single transaction."""
        db = self.db_mgr.get_session()
        links_added = 0
        try:
            for source_url, outgoing_links in batch_links:
                norm_src = self.normalizer.normalize(source_url)
                if not norm_src:
                    continue
                src_domain = urlparse(norm_src).hostname or ""
                seen_targets: Set[str] = set()

                for raw_tgt in outgoing_links:
                    norm_tgt = self.normalizer.normalize(raw_tgt, base_url=norm_src)
                    if not norm_tgt or norm_tgt == norm_src or norm_tgt in seen_targets:
                        continue
                    seen_targets.add(norm_tgt)
                    tgt_domain = urlparse(norm_tgt).hostname or ""

                    db.add(
                        PageLink(
                            source_url=norm_src,
                            target_url=norm_tgt,
                            source_domain=src_domain,
                            target_domain=tgt_domain,
                        )
                    )
                    links_added += 1

            db.commit()
            return links_added
        except Exception as e:
            db.rollback()
            logger.error("Batch link recording failed: %s", e)
            return 0
        finally:
            db.close()

    def compute_and_save_authority(
        self,
        snapshot_version: str = "v1",
        damping: float = 0.85,
    ) -> Dict[str, Any]:
        """
        Reconstruct graph from DB, execute PageRank, and update page_authority table.
        """
        db = self.db_mgr.get_session()
        try:
            # 1. Fetch all known canonical URLs in the frontier
            urls = [r[0] for r in db.query(URLRecord.url).all()]
            nodes: Set[str] = set(urls)

            # 2. Fetch all directed links
            link_rows = db.query(PageLink.source_url, PageLink.target_url).all()
            edges: List[Tuple[str, str]] = [(row[0], row[1]) for row in link_rows]

            # 3. Compute PageRank
            calc = PageRankCalculator(damping=damping)
            ranks = calc.compute(nodes, edges)

            # 4. Calculate degrees
            in_degrees: Dict[str, int] = {n: 0 for n in nodes}
            out_degrees: Dict[str, int] = {n: 0 for n in nodes}
            for src, tgt in edges:
                if src in out_degrees:
                    out_degrees[src] += 1
                if tgt in in_degrees:
                    in_degrees[tgt] += 1

            # 5. Persist to page_authority efficiently
            now = datetime.now(timezone.utc)
            existing_map = {row.url: row for row in db.query(PageAuthority).all()}
            for url, pr in ranks.items():
                domain = urlparse(url).hostname or ""
                existing = existing_map.get(url)
                if existing:
                    existing.pagerank = pr
                    existing.in_degree = in_degrees.get(url, 0)
                    existing.out_degree = out_degrees.get(url, 0)
                    existing.snapshot_version = snapshot_version
                    existing.computed_at = now
                else:
                    rec = PageAuthority(
                        url=url,
                        canonical_url=url,
                        domain=domain,
                        pagerank=pr,
                        in_degree=in_degrees.get(url, 0),
                        out_degree=out_degrees.get(url, 0),
                        snapshot_version=snapshot_version,
                        computed_at=now,
                    )
                    db.add(rec)

            db.commit()

            return {
                "nodes_count": len(ranks),
                "edges_count": len(edges),
                "snapshot_version": snapshot_version,
                "top_authority": sorted(ranks.items(), key=lambda x: x[1], reverse=True)[:5],
            }
        except Exception as e:
            db.rollback()
            logger.error("Error computing link authority: %s", e)
            raise
        finally:
            db.close()
