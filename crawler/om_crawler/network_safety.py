import ipaddress
import socket
from urllib.parse import urlparse
from typing import Tuple, List, Optional

# Disallowed IP networks for SSRF and private destination defense
FORBIDDEN_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),          # Current network (only valid as source address)
    ipaddress.ip_network("10.0.0.0/8"),         # Private-Use (RFC 1918)
    ipaddress.ip_network("100.64.0.0/10"),      # Shared Address Space (RFC 6598)
    ipaddress.ip_network("127.0.0.0/8"),        # Loopback (RFC 1122)
    ipaddress.ip_network("169.254.0.0/16"),     # Link Local / Cloud Metadata (RFC 3927)
    ipaddress.ip_network("172.16.0.0/12"),      # Private-Use (RFC 1918)
    ipaddress.ip_network("192.0.0.0/24"),       # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),       # Documentation (TEST-NET-1)
    ipaddress.ip_network("192.168.0.0/16"),     # Private-Use (RFC 1918)
    ipaddress.ip_network("198.18.0.0/15"),      # Benchmarking
    ipaddress.ip_network("198.51.100.0/24"),    # Documentation (TEST-NET-2)
    ipaddress.ip_network("203.0.113.0/24"),     # Documentation (TEST-NET-3)
    ipaddress.ip_network("224.0.0.0/4"),        # Multicast
    ipaddress.ip_network("240.0.0.0/4"),        # Reserved
    ipaddress.ip_network("255.255.255.255/32"), # Limited Broadcast
    # IPv6 ranges
    ipaddress.ip_network("::/128"),             # Unspecified
    ipaddress.ip_network("::1/128"),            # Loopback
    ipaddress.ip_network("fc00::/7"),           # Unique Local (ULA)
    ipaddress.ip_network("fe80::/10"),          # Link-Local Unicast
    ipaddress.ip_network("ff00::/8"),           # Multicast
]

# Explicit metadata hostnames
CLOUD_METADATA_HOSTS = {
    "metadata.google.internal",
    "metadata.internal",
    "instance-data",
    "169.254.169.254",
}

# Max allowed HTML document size (2MB)
MAX_RESPONSE_BYTES = 2 * 1024 * 1024

# Allowed content types
ALLOWED_CONTENT_TYPES = (
    "text/html",
    "application/xhtml+xml",
    "text/xml",
    "application/xml",
)


def is_safe_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if the IP address is globally reachable and not private/loopback/cloud-metadata."""
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return False
    for forbidden in FORBIDDEN_NETWORKS:
        if ip in forbidden:
            return False
    return True


def resolve_and_validate_host(hostname: str) -> Tuple[bool, str, List[str]]:
    """
    Resolve DNS for a hostname and verify that NONE of the resolved IPs belong to private or cloud-metadata ranges.
    Returns (is_valid, reason, resolved_ips).
    """
    cleaned_host = hostname.strip().lower()
    if not cleaned_host:
        return False, "Empty hostname", []

    if cleaned_host in CLOUD_METADATA_HOSTS:
        return False, f"Blocked cloud metadata destination: {cleaned_host}", []

    # Check if host is already an IP address literal
    try:
        ip_obj = ipaddress.ip_address(cleaned_host)
        if not is_safe_ip(ip_obj):
            return False, f"Blocked private/reserved IP: {ip_obj}", [str(ip_obj)]
        return True, "Safe IP", [str(ip_obj)]
    except ValueError:
        pass  # Host is a domain name, proceed to DNS resolution

    try:
        addr_info = socket.getaddrinfo(cleaned_host, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        return False, f"DNS resolution failed: {e}", []
    except Exception as e:
        return False, f"DNS error: {e}", []

    resolved_ips = []
    for family, _, _, _, sockaddr in addr_info:
        ip_str = sockaddr[0]
        resolved_ips.append(ip_str)
        try:
            ip_obj = ipaddress.ip_address(ip_str)
            if not is_safe_ip(ip_obj):
                return False, f"Destination resolved to forbidden IP ({ip_str})", resolved_ips
        except ValueError:
            return False, f"Malformed IP address resolved ({ip_str})", resolved_ips

    if not resolved_ips:
        return False, "No IP addresses resolved", []

    return True, "Safe destination", resolved_ips


def validate_url_security(url: str, check_dns: bool = True) -> Tuple[bool, str]:
    """
    Full security validation for a crawl target URL:
    - Scheme must be http or https
    - No userinfo / embedded credentials (user:pass@host)
    - Valid host
    - Safe destination IP addresses (anti-SSRF)
    """
    if not url or not isinstance(url, str):
        return False, "URL must be a non-empty string"

    url = url.strip()
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Malformed URL: {e}"

    if parsed.scheme.lower() not in ("http", "https"):
        return False, f"Unsupported scheme: {parsed.scheme} (only HTTP/HTTPS allowed)"

    if parsed.username or parsed.password:
        return False, "URLs with embedded credentials are prohibited"

    if not parsed.hostname:
        return False, "Missing hostname in URL"

    if check_dns:
        safe, reason, _ = resolve_and_validate_host(parsed.hostname)
        if not safe:
            return False, reason

    return True, "URL is safe"


def is_allowed_content_type(content_type: Optional[str]) -> bool:
    """Validate that HTTP Content-Type header corresponds to HTML/XHTML."""
    if not content_type:
        return False
    lower = content_type.lower().split(";")[0].strip()
    return any(lower == allowed for allowed in ALLOWED_CONTENT_TYPES)
