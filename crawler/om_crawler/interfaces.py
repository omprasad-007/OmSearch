from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime


class IRobotsParser(ABC):
    """Interface for robots.txt fetching and rule enforcement."""

    @abstractmethod
    def is_allowed(self, user_agent: str, url: str) -> bool:
        """Return True if URL crawling is permitted by robots.txt."""
        pass

    @abstractmethod
    def get_crawl_delay(self, user_agent: str, domain: str) -> Optional[float]:
        """Return crawl delay in seconds if specified."""
        pass


class IFrontier(ABC):
    """Interface for persistent URL crawl frontier and politeness queuing."""

    @abstractmethod
    def add_url(self, url: str, priority: int = 0, depth: int = 0) -> bool:
        """Enqueue URL into crawl frontier."""
        pass

    @abstractmethod
    def next_url(self) -> Optional[Dict[str, Any]]:
        """Retrieve next schedulable URL according to politeness policies."""
        pass

    @abstractmethod
    def mark_completed(self, url: str, status_code: int) -> None:
        """Record successful fetch."""
        pass

    @abstractmethod
    def mark_failed(self, url: str, error: str) -> None:
        """Record failed fetch and manage retry budget."""
        pass


class IDocumentParser(ABC):
    """Interface for HTML parsing, link extraction and content extraction."""

    @abstractmethod
    def extract_text(self, raw_html: str) -> Dict[str, Any]:
        """Extract title, clean text body, language, and metadata."""
        pass

    @abstractmethod
    def extract_links(self, raw_html: str, base_url: str) -> List[str]:
        """Extract outgoing links normalized against base_url."""
        pass


class ICrawler(ABC):
    """Base crawler abstraction for standalone and Scrapy-based crawlers."""

    @abstractmethod
    def start(self, seed_urls: List[str]) -> None:
        """Start crawl run with initial seed URLs."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Politely stop active crawler workers."""
        pass
