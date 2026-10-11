import time
import logging
from urllib.parse import urlparse
from typing import Dict, Optional, Tuple
import httpx
from protego import Protego

from crawler.om_crawler.network_safety import validate_url_security

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "OMSearchBot/0.2 (+https://omsearch.org/bot; bot@omsearch.org)"
DEFAULT_CACHE_TTL_SECONDS = 86400  # 24 hours
DEFAULT_PER_HOST_DELAY = 2.0       # 2 seconds between requests to same host


class RobotsCacheEntry:
    def __init__(
        self,
        parser: Optional[Protego],
        fetched_at: float,
        status_code: int,
        allow_all: bool = False,
        disallow_all: bool = False,
    ):
        self.parser = parser
        self.fetched_at = fetched_at
        self.status_code = status_code
        self.allow_all = allow_all
        self.disallow_all = disallow_all
        self.crawl_delay: Optional[float] = None
        if parser:
            try:
                delay = parser.crawl_delay(DEFAULT_USER_AGENT)
                if delay is not None:
                    self.crawl_delay = max(float(delay), DEFAULT_PER_HOST_DELAY)
            except Exception:
                pass


class RobotsPolicyManager:
    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        cache_ttl: float = DEFAULT_CACHE_TTL_SECONDS,
        default_delay: float = DEFAULT_PER_HOST_DELAY,
    ):
        self.user_agent = user_agent
        self.cache_ttl = cache_ttl
        self.default_delay = default_delay
        self._cache: Dict[str, RobotsCacheEntry] = {}
        self._last_host_access: Dict[str, float] = {}
        self._disabled_domains: set[str] = set()
        self._global_paused: bool = False

    def set_global_pause(self, paused: bool) -> None:
        """Emergency global pause switch."""
        self._global_paused = paused
        logger.warning("Crawler global pause state changed to: %s", paused)

    def is_globally_paused(self) -> bool:
        return self._global_paused

    def disable_domain(self, domain: str) -> None:
        """Emergency per-domain disable mechanism."""
        self._disabled_domains.add(domain.lower().strip())
        logger.warning("Crawler emergency disable added for domain: %s", domain)

    def enable_domain(self, domain: str) -> None:
        self._disabled_domains.discard(domain.lower().strip())

    def is_domain_disabled(self, domain: str) -> bool:
        dom = domain.lower().strip()
        return any(dom == d or dom.endswith("." + d) for d in self._disabled_domains)

    def get_robots_url(self, target_url: str) -> str:
        """Derive standard http(s)://domain/robots.txt URL."""
        parsed = urlparse(target_url)
        return f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    def fetch_robots_txt(self, target_url: str) -> RobotsCacheEntry:
        """Fetch and parse robots.txt for the given target domain, or return cached parser."""
        parsed = urlparse(target_url)
        host_key = f"{parsed.scheme}://{parsed.netloc}"
        now = time.time()

        if host_key in self._cache:
            entry = self._cache[host_key]
            if now - entry.fetched_at < self.cache_ttl:
                return entry

        robots_url = self.get_robots_url(target_url)

        # Validate robots.txt URL security (anti-SSRF check)
        is_safe, sec_reason = validate_url_security(robots_url, check_dns=True)
        if not is_safe:
            logger.warning("Refusing to fetch robots.txt for unsafe destination %s: %s", robots_url, sec_reason)
            entry = RobotsCacheEntry(parser=None, fetched_at=now, status_code=403, disallow_all=True)
            self._cache[host_key] = entry
            return entry

        try:
            with httpx.Client(timeout=4.0, follow_redirects=True) as client:
                resp = client.get(robots_url, headers={"User-Agent": self.user_agent})
                status_code = resp.status_code

                if status_code == 200:
                    parser = Protego.parse(resp.text)
                    entry = RobotsCacheEntry(parser=parser, fetched_at=now, status_code=200)
                elif status_code in (404, 410):
                    # 404/410 means no restrictions
                    entry = RobotsCacheEntry(parser=None, fetched_at=now, status_code=status_code, allow_all=True)
                else:
                    # 5xx or 403 Forbidden: conservative approach, disallow
                    entry = RobotsCacheEntry(parser=None, fetched_at=now, status_code=status_code, disallow_all=True)

        except Exception as e:
            logger.debug("Failed to fetch robots.txt from %s: %s (treating conservatively)", robots_url, e)
            entry = RobotsCacheEntry(parser=None, fetched_at=now, status_code=500, disallow_all=True)

        self._cache[host_key] = entry
        return entry

    def is_allowed(self, url: str) -> Tuple[bool, str]:
        """
        Check if URL is permitted according to:
        1. Emergency global pause
        2. Per-domain disable
        3. Parsed robots.txt rules (Protego)
        """
        if self._global_paused:
            return False, "Crawler is globally paused by operator"

        parsed = urlparse(url)
        domain = parsed.hostname or ""
        if self.is_domain_disabled(domain):
            return False, f"Domain {domain} is explicitly disabled by operator"

        entry = self.fetch_robots_txt(url)
        if entry.disallow_all:
            return False, "Disallowed by robots.txt (server error or conservative block)"

        if entry.allow_all:
            return True, "Allowed (no robots.txt restrictions)"

        if entry.parser:
            allowed = entry.parser.can_fetch(url, self.user_agent)
            if not allowed:
                return False, "Blocked by robots.txt directive"

        return True, "Allowed by robots.txt"

    def get_crawl_delay(self, target_url: str) -> float:
        """Return the per-host rate limit delay in seconds."""
        parsed = urlparse(target_url)
        host_key = f"{parsed.scheme}://{parsed.netloc}"
        if host_key in self._cache and self._cache[host_key].crawl_delay:
            return self._cache[host_key].crawl_delay
        return self.default_delay

    def record_host_access(self, host: str) -> None:
        """Track timestamp of most recent request to this host."""
        self._last_host_access[host.lower()] = time.time()

    def get_time_until_next_request(self, target_url: str) -> float:
        """Return seconds to wait before making another request to this host."""
        parsed = urlparse(target_url)
        host = parsed.netloc.lower()
        last_time = self._last_host_access.get(host, 0)
        delay = self.get_crawl_delay(target_url)
        elapsed = time.time() - last_time
        if elapsed < delay:
            return delay - elapsed
        return 0.0
