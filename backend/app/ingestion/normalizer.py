import hashlib
import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

# Tracking query parameters to remove during normalization
TRACKING_PARAMS = {
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
    "source",
}


def normalize_url(url: str) -> str:
    """
    Standardizes a URL to a canonical format:
    - Lowercase scheme and netloc
    - Strip default ports (80 for http, 443 for https)
    - Strip URL fragments (#hash)
    - Remove tracking query parameters
    - Sort query parameters alphabetically
    - Normalize trailing slashes (keep single slash for root, strip for paths)
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL must be a non-empty string")

    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Strip default ports
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    # Clean path: normalize slashes
    path = parsed.path or "/"
    # Clean redundant duplicate slashes
    path = re.sub(r"/+", "/", path)
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]

    # Filter and sort query parameters
    query_items = parse_qsl(parsed.query, keep_blank_values=False)
    filtered_params = [
        (k, v) for k, v in query_items
        if k.lower() not in TRACKING_PARAMS
    ]
    filtered_params.sort(key=lambda x: (x[0], x[1]))
    new_query = urlencode(filtered_params)

    # Reconstruct normalized URL (fragment omitted)
    canonical = urlunparse((scheme, netloc, path, "", new_query, ""))
    return canonical


def extract_domain(url: str) -> str:
    """Extract host domain from URL."""
    parsed = urlparse(normalize_url(url))
    domain = parsed.netloc
    # Strip any port if still present
    if ":" in domain:
        domain = domain.split(":")[0]
    return domain


def compute_url_id(canonical_url: str) -> str:
    """Deterministic document ID generated from canonical URL SHA-256."""
    return hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:24]


def compute_content_hash(text: str) -> str:
    """
    Compute SHA-256 hash of whitespace-collapsed text for deduplication.
    """
    collapsed = " ".join(text.split()).strip().lower()
    return hashlib.sha256(collapsed.encode("utf-8")).hexdigest()


def generate_snippet(text: str, max_length: int = 240) -> str:
    """
    Produce a clean, concise snippet from text body.
    """
    collapsed = " ".join(text.split()).strip()
    if len(collapsed) <= max_length:
        return collapsed
    # Cut at word boundary
    truncated = collapsed[:max_length]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated + "..."
