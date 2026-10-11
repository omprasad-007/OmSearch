import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import trafilatura

from crawler.om_crawler.url_normalizer import URLNormalizer

logger = logging.getLogger(__name__)


class ExtractedDocument:
    def __init__(
        self,
        url: str,
        final_url: str,
        title: str,
        main_text: str,
        meta_description: str,
        canonical_url: Optional[str],
        language: str,
        domain: str,
        http_status: int,
        content_type: str,
        content_hash: str,
        fetched_at: datetime,
        published_at: Optional[datetime],
        outgoing_links: List[str],
    ):
        self.url = url
        self.final_url = final_url
        self.title = title
        self.main_text = main_text
        self.meta_description = meta_description
        self.canonical_url = canonical_url
        self.language = language
        self.domain = domain
        self.http_status = http_status
        self.content_type = content_type
        self.content_hash = content_hash
        self.fetched_at = fetched_at
        self.published_at = published_at
        self.outgoing_links = outgoing_links

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "final_url": self.final_url,
            "title": self.title,
            "content": self.main_text,
            "snippet": self.meta_description or (self.main_text[:200] + "..."),
            "canonical_url": self.canonical_url or self.final_url,
            "language": self.language,
            "domain": self.domain,
            "http_status": self.http_status,
            "content_type": self.content_type,
            "content_hash": self.content_hash,
            "fetched_at": self.fetched_at.isoformat(),
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "outgoing_links": self.outgoing_links,
        }


class HTMLExtractor:
    def __init__(self, normalizer: Optional[URLNormalizer] = None):
        self.normalizer = normalizer or URLNormalizer()

    def extract(
        self,
        html_content: str,
        url: str,
        final_url: Optional[str] = None,
        http_status: int = 200,
        content_type: str = "text/html",
        fetched_at: Optional[datetime] = None,
    ) -> ExtractedDocument:
        effective_url = final_url or url
        fetch_time = fetched_at or datetime.now(timezone.utc)
        domain = urlparse(effective_url).hostname or ""

        title = ""
        main_text = ""
        meta_description = ""
        canonical_raw = None
        language = "en"
        published_at = None
        outgoing_links: List[str] = []

        if not html_content or not html_content.strip():
            content_hash = hashlib.sha256(b"").hexdigest()
            return ExtractedDocument(
                url=url,
                final_url=effective_url,
                title="",
                main_text="",
                meta_description="",
                canonical_url=None,
                language="en",
                domain=domain,
                http_status=http_status,
                content_type=content_type,
                content_hash=content_hash,
                fetched_at=fetch_time,
                published_at=None,
                outgoing_links=[],
            )

        # 1. Parse using BeautifulSoup for tags, metadata and links
        soup = BeautifulSoup(html_content, "html.parser")

        # Extract title
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        # Meta description
        meta_desc_tag = (
            soup.find("meta", attrs={"name": lambda x: x and x.lower() == "description"})
            or soup.find("meta", attrs={"property": "og:description"})
        )
        if meta_desc_tag and meta_desc_tag.get("content"):
            meta_description = meta_desc_tag["content"].strip()

        # Canonical tag
        canon_tag = soup.find("link", attrs={"rel": lambda x: x and "canonical" in x.lower()})
        if canon_tag and canon_tag.get("href"):
            canonical_raw = canon_tag["href"].strip()

        # Language tag
        html_tag = soup.find("html")
        if html_tag and html_tag.get("lang"):
            lang_attr = html_tag["lang"].strip().lower()
            language = lang_attr.split("-")[0] if "-" in lang_attr else lang_attr

        # Extract outgoing links
        for a in soup.find_all("a", href=True):
            raw_href = a["href"].strip()
            if raw_href and not raw_href.startswith(("#", "javascript:", "mailto:", "tel:")):
                norm_link = self.normalizer.normalize(raw_href, base_url=effective_url)
                if norm_link and norm_link not in outgoing_links:
                    outgoing_links.append(norm_link)

        # 2. Extract main text using Trafilatura
        try:
            traf_result = trafilatura.extract(
                html_content,
                url=effective_url,
                include_links=False,
                include_images=False,
                include_tables=True,
                no_fallback=False,
                favor_recall=True,
            )
            if traf_result and len(traf_result.strip()) > 30:
                main_text = traf_result.strip()

            # Attempt metadata from Trafilatura
            meta = trafilatura.extract_metadata(html_content, default_url=effective_url)
            if meta:
                if not title and meta.title:
                    title = meta.title.strip()
                if not meta_description and meta.description:
                    meta_description = meta.description.strip()
                if not canonical_raw and meta.canonicalurl:
                    canonical_raw = meta.canonicalurl.strip()
                if meta.date:
                    try:
                        published_at = datetime.fromisoformat(meta.date)
                    except Exception:
                        pass
        except Exception as te:
            logger.debug("Trafilatura extraction warning for %s: %s", effective_url, te)

        # 3. Fallback to BeautifulSoup clean text if Trafilatura yielded little text
        if not main_text:
            # Strip non-content elements
            for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "aside"]):
                tag.decompose()
            main_text = soup.get_text(separator=" ", strip=True)

        if not title:
            # Fallback title to domain or h1
            h1 = soup.find("h1")
            if h1 and h1.get_text(strip=True):
                title = h1.get_text(strip=True)
            else:
                title = domain

        # Validate canonical URL
        validated_canonical = None
        if canonical_raw:
            validated_canonical = self.normalizer.validate_canonical(canonical_raw, effective_url)

        # Compute content hash for deduplication
        collapsed = " ".join(main_text.split()).strip().lower()
        content_hash = hashlib.sha256(collapsed.encode("utf-8")).hexdigest()

        return ExtractedDocument(
            url=url,
            final_url=effective_url,
            title=title,
            main_text=main_text,
            meta_description=meta_description,
            canonical_url=validated_canonical,
            language=language or "en",
            domain=domain,
            http_status=http_status,
            content_type=content_type,
            content_hash=content_hash,
            fetched_at=fetch_time,
            published_at=published_at,
            outgoing_links=outgoing_links,
        )
