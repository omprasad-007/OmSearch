import argparse
import sys
import json
from pathlib import Path

# Add backend to path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "backend"))

from app.core.logging import setup_logging
from app.repositories.database import get_db_manager, CrawlJob
from crawler.om_crawler.frontier import FrontierManager
from crawler.om_crawler.crawler_engine import CrawlerEngine

setup_logging(level="INFO")


def cmd_start(args):
    seeds = [s.strip() for s in args.seeds.split(",") if s.strip()]
    if not seeds:
        print("Error: At least one seed URL must be specified via --seeds")
        sys.exit(1)

    allowed = [d.strip() for d in args.allowed_domains.split(",") if d.strip()] if args.allowed_domains else None

    db = get_db_manager().get_session()
    job = CrawlJob(
        job_type="cli_crawl",
        status="pending",
        config=json.dumps({
            "seed_urls": seeds,
            "max_pages": args.max_pages,
            "max_depth": args.max_depth,
            "allowed_domains": allowed,
            "rate_limit_delay": args.delay,
        }),
        total_urls=len(seeds),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    job_id = job.id
    db.close()

    print(f"Created Crawl Job #{job_id}. Starting CrawlerEngine...")
    engine = CrawlerEngine(
        job_id=job_id,
        seed_urls=seeds,
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        allowed_domains=allowed,
        rate_limit_delay=args.delay,
    )
    result = engine.run()
    print("\n--- Crawl Job Finished ---")
    print(f"Status:    {result.get('status')}")
    print(f"Processed: {result.get('processed')}")
    print(f"Indexed:   {result.get('indexed')}")
    print(f"Failed:    {result.get('failed')}")
    print("---------------------------\n")


def cmd_stats(args):
    frontier = FrontierManager()
    stats = frontier.get_stats()
    print("\n--- Crawl Frontier Statistics ---")
    print(f"Total Discovered URLs: {stats['total_urls']}")
    print(f"Distinct Domains:     {stats['total_domains']}")
    print("Counts by Status:")
    for status, count in stats["by_status"].items():
        if count > 0:
            print(f"  {status:<16}: {count}")
    print("---------------------------------\n")


def cmd_failures(args):
    from app.repositories.database import URLRecord, FrontierStatus
    db = get_db_manager().get_session()
    try:
        failures = (
            db.query(URLRecord)
            .filter(URLRecord.status.in_([FrontierStatus.FAILED, FrontierStatus.BLOCKED, FrontierStatus.SKIPPED_POLICY]))
            .order_by(URLRecord.updated_at.desc())
            .limit(args.limit)
            .all()
        )
        print(f"\n--- Recent Crawl Failures (Limit: {args.limit}) ---")
        if not failures:
            print("No failures recorded.")
        for f in failures:
            print(f"[{f.status}] URL: {f.url}")
            print(f"  Domain: {f.domain} | Attempts: {f.attempt_count} | HTTP: {f.http_status}")
            print(f"  Reason: {f.last_error}\n")
        print("--------------------------------------------------\n")
    finally:
        db.close()


def cmd_reset_leases(args):
    frontier = FrontierManager()
    count = frontier.reset_expired_leases()
    print(f"Reclaimed {count} expired worker leases.")


def main():
    parser = argparse.ArgumentParser(description="OM Search - Crawler CLI Management Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # start
    p_start = subparsers.add_parser("start", help="Start a crawl run")
    p_start.add_argument("--seeds", required=True, help="Comma-separated seed URLs")
    p_start.add_argument("--max-pages", type=int, default=20, help="Max pages to crawl")
    p_start.add_argument("--max-depth", type=int, default=2, help="Max link crawl depth")
    p_start.add_argument("--allowed-domains", default=None, help="Comma-separated allowed domains")
    p_start.add_argument("--delay", type=float, default=1.0, help="Per-host rate limit delay in seconds")

    # stats
    subparsers.add_parser("stats", help="View frontier statistics")

    # failures
    p_fail = subparsers.add_parser("failures", help="View recent crawl failures")
    p_fail.add_argument("--limit", type=int, default=20, help="Max failure records to show")

    # reset-leases
    subparsers.add_parser("reset-leases", help="Reset expired worker leases")

    args = parser.parse_args()
    if args.command == "start":
        cmd_start(args)
    elif args.command == "stats":
        cmd_stats(args)
    elif args.command == "failures":
        cmd_failures(args)
    elif args.command == "reset-leases":
        cmd_reset_leases(args)


if __name__ == "__main__":
    main()
