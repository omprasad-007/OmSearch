import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode, urljoin
from typing import Optional, Set, List, Tuple

# Tracking query parameters to remove
TRACKING_PARAMS: Set[str] = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "_hsenc",
    "_hsmi",
    "ref",
    "ref_src",
    "source",
    "_ga",
    "_gl",
    "yclid",
}

# File extensions to reject from crawling
FORBIDDEN_EXTENSIONS: Set[str] = {
    ".pdf", ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv",
    ".exe", ".bin", ".dmg", ".iso", ".msi", ".apk",
    ".css", ".js", ".json", ".xml", ".woff", ".woff2", ".ttf", ".eot",
}

# Standard URL path patterns to ignore
FORBIDDEN_PATH_PATTERNS = [
    re.compile(r"/(?:wp-admin|wp-login|login|logout|signin|signout|cart|checkout)/?", re.I),
]


class URLNormalizer:
    def __init__(
        self,
        allowed_domains: Optional[List[str]] = None,
        denied_domains: Optional[List[str]] = None,
        max_depth: int = 3,
    ):
        self.allowed_domains = {d.lower().strip() for d in allowed_domains} if allowed_domains else set()
        self.denied_domains = {d.lower().strip() for d in denied_domains} if denied_domains else set()
        self.max_depth = max_depth

    def normalize(self, raw_url: str, base_url: Optional[str] = None) -> Optional[str]:
        """
        Normalize and canonicalize a URL string.
        Resolves relative URLs against base_url if provided.
        Returns normalized URL or None if invalid.
        """
        if not raw_url or not isinstance(raw_url, str):
            return None

        clean = raw_url.strip()
        if not clean:
            return None

        # Resolve relative links
        if base_url:
            try:
                clean = urljoin(base_url, clean)
            except Exception:
                return None

        # Scheme check
        try:
            parsed = urlparse(clean)
        except Exception:
            return None

        scheme = parsed.scheme.lower()
        if scheme not in ("http", "https"):
            return None

        # Hostname check
        netloc = parsed.netloc.lower()
        if not netloc:
            return None

        # Strip default ports
        if scheme == "http" and netloc.endswith(":80"):
            netloc = netloc[:-3]
        elif scheme == "https" and netloc.endswith(":443"):
            netloc = netloc[:-4]

        # Check credentials
        if "@" in netloc:
            # Embedded credentials are prohibited
            return None

        # Normalize path
        path = parsed.path or "/"
        # Collapse multiple consecutive slashes
        path = re.sub(r"/+", "/", path)

        # Do not strip trailing slash if it is root "/"
        if len(path) > 1 and path.endswith("/"):
            path = path[:-1]

        # Filter out tracking query params while preserving content params
        query_items = parse_qsl(parsed.query, keep_blank_values=False)
        filtered = [
            (k, v) for k, v in query_items
            if k.lower() not in TRACKING_PARAMS
        ]
        filtered.sort(key=lambda x: (x[0], x[1]))
        clean_query = urlencode(filtered)

        # Construct normalized URL (fragment dropped)
        normalized = urlunparse((scheme, netloc, path, "", clean_query, ""))
        return normalized

    def is_crawlable(self, normalized_url: str, current_depth: int = 0) -> Tuple[bool, str]:
        """
        Check if a normalized URL is eligible for crawling.
        Validates depth, extensions, path patterns, allowlists, and denylists.
        """
        if not normalized_url:
            return False, "Empty or invalid URL"

        if current_depth > self.max_depth:
            return False, f"Exceeded maximum crawl depth ({current_depth} > {self.max_depth})"

        try:
            parsed = urlparse(normalized_url)
        except Exception:
            return False, "Failed to parse URL"

        domain = parsed.hostname.lower() if parsed.hostname else ""
        if not domain:
            return False, "Missing hostname"

        # Check domain allowlist
        if self.allowed_domains:
            matched = any(domain == d or domain.endswith("." + d) for d in self.allowed_domains)
            if not matched:
                return False, f"Domain {domain} not in allowlist"

        # Check domain denylist
        if self.denied_domains:
            blocked = any(domain == d or domain.endswith("." + d) for d in self.denied_domains)
            if blocked:
                return False, f"Domain {domain} is in denylist"

        # Check forbidden file extensions
        path = parsed.path.lower()
        for ext in FORBIDDEN_EXTENSIONS:
            if path.endswith(ext):
                return False, f"Forbidden file extension: {ext}"

        # Check forbidden path patterns
        for pattern in FORBIDDEN_PATH_PATTERNS:
            if pattern.search(path):
                return False, "Matches blocked path pattern"

        return True, "Eligible for crawl"

    def validate_canonical(self, canonical_url: str, current_url: str) -> Optional[str]:
        """
        Validate rel=canonical tag found on a page.
        Does not blindly trust canonical URLs if malformed or cross-domain without authorization.
        """
        norm_canonical = self.normalize(canonical_url, base_url=current_url)
        if not norm_canonical:
            return None

        curr_domain = urlparse(current_url).hostname
        canon_domain = urlparse(norm_canonical).hostname

        if not curr_domain or not canon_domain:
            return None

        # Allow same domain or same second-level domain
        if curr_domain == canon_domain:
            return norm_canonical

        # If allowed domains configured, check if both are in allowlist
        if self.allowed_domains:
            if canon_domain in self.allowed_domains:
                return norm_canonical

        return None
