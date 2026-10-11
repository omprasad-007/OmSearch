from protego import Protego
from crawler.om_crawler.robots_policy import RobotsPolicyManager, RobotsCacheEntry


def test_robots_manager_parser_rules():
    manager = RobotsPolicyManager()

    # Create mock Protego parser with Disallow: /admin/ and Allow: /admin/public
    robots_text = """
    User-agent: *
    Disallow: /admin/
    Allow: /admin/public
    Crawl-delay: 5
    """
    parser = Protego.parse(robots_text)

    host_key = "https://example.com"
    entry = RobotsCacheEntry(parser=parser, fetched_at=1000000000.0, status_code=200)
    entry.crawl_delay = 5.0
    manager._cache[host_key] = entry
    manager.cache_ttl = 999999999

    # Check allow/disallow
    assert not manager.is_allowed("https://example.com/admin/settings")[0]
    assert manager.is_allowed("https://example.com/admin/public")[0]
    assert manager.is_allowed("https://example.com/blog")[0]
    assert manager.get_crawl_delay("https://example.com/blog") == 5.0


def test_robots_emergency_global_pause():
    manager = RobotsPolicyManager()
    manager.set_global_pause(True)
    allowed, reason = manager.is_allowed("https://example.com/page")
    assert not allowed
    assert "globally paused" in reason.lower()


def test_robots_emergency_domain_disable():
    manager = RobotsPolicyManager()
    manager.disable_domain("spamsite.com")
    allowed, reason = manager.is_allowed("https://spamsite.com/article")
    assert not allowed
    assert "explicitly disabled" in reason.lower()
