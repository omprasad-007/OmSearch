import ipaddress
import pytest
from crawler.om_crawler.network_safety import (
    is_safe_ip,
    validate_url_security,
    is_allowed_content_type,
)


def test_is_safe_ip_blocks_private_and_loopback():
    assert not is_safe_ip(ipaddress.ip_address("127.0.0.1"))
    assert not is_safe_ip(ipaddress.ip_address("10.0.0.1"))
    assert not is_safe_ip(ipaddress.ip_address("192.168.1.100"))
    assert not is_safe_ip(ipaddress.ip_address("172.16.0.5"))
    assert not is_safe_ip(ipaddress.ip_address("169.254.169.254"))  # AWS / Cloud metadata
    assert not is_safe_ip(ipaddress.ip_address("::1"))


def test_is_safe_ip_allows_public_ip():
    assert is_safe_ip(ipaddress.ip_address("93.184.216.34"))  # example.com
    assert is_safe_ip(ipaddress.ip_address("8.8.8.8"))


def test_validate_url_security_blocks_embedded_credentials():
    safe, reason = validate_url_security("http://admin:secret@example.com/page", check_dns=False)
    assert not safe
    assert "embedded credentials" in reason.lower()


def test_validate_url_security_blocks_invalid_schemes():
    assert not validate_url_security("ftp://example.com/file", check_dns=False)[0]
    assert not validate_url_security("javascript:alert(1)", check_dns=False)[0]
    assert not validate_url_security("file:///etc/passwd", check_dns=False)[0]


def test_validate_url_security_accepts_valid_http_https():
    safe, _ = validate_url_security("https://example.com/docs", check_dns=False)
    assert safe


def test_is_allowed_content_type():
    assert is_allowed_content_type("text/html; charset=UTF-8")
    assert is_allowed_content_type("application/xhtml+xml")
    assert not is_allowed_content_type("application/pdf")
    assert not is_allowed_content_type("image/png")
    assert not is_allowed_content_type("application/octet-stream")
    assert not is_allowed_content_type(None)
