"""
OM Search - Common Crawl and Multi-Domain Archive Streamer
Handles WARC/WET records, partitioned JSONL archives, multi-domain web extractions,
and high-throughput chunk generation for Phase 4 massive scale (100k, 1M, 10M pages).
"""
import os
import re
import gzip
import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Generator, Optional
from urllib.parse import urlparse

from app.ingestion.normalizer import normalize_url, compute_url_id, generate_snippet

logger = logging.getLogger("om_crawler.common_crawl")

# Curated High-Authority Multi-Domain Ecosystem for Phase 4
MULTI_DOMAIN_TAXONOMY = {
    "Technology & Engineering": [
        ("docs.python.org", "Python 3 Standard Library Documentation and Language Reference"),
        ("developer.mozilla.org", "MDN Web Docs - HTML, CSS, JavaScript, and Web APIs"),
        ("rust-lang.org", "The Rust Programming Language - Fast, Safe, Concurrent Systems"),
        ("github.com", "Open Source Software Repositories, Packages, and Source Code"),
        ("stackoverflow.com", "Developer Q&A, Algorithms, Software Debugging, and Solutions"),
        ("kernel.org", "Linux Kernel Architecture, Drivers, Scheduling, and Syscalls"),
        ("kubernetes.io", "Container Orchestration, Pod Scheduling, Ingress, and Services"),
        ("docker.com", "Containerization Runtime, Image Layering, and Microservices"),
        ("postgresql.org", "Relational Database Management System, MVCC, and B-Tree Indexes"),
        ("redis.io", "In-Memory Data Store, Caching, Pub/Sub, and High Throughput K/V"),
        ("w3.org", "World Wide Web Standards, Semantic Web, and Accessibility Guidelines"),
        ("apache.org", "Apache Software Foundation - Distributed Systems and Big Data"),
    ],
    "Science & Academia": [
        ("arxiv.org", "Cornell University Open Access Research Papers - Physics, AI, Math"),
        ("nature.com", "International Journal of Science, Biology, and Biotechnology"),
        ("nasa.gov", "Aeronautics, Deep Space Exploration, James Webb, and Astronomy"),
        ("mit.edu", "Massachusetts Institute of Technology OpenCourseWare and Research"),
        ("stanford.edu", "Stanford Artificial Intelligence, Stanford Encyclopedia of Philosophy"),
        ("cern.ch", "Large Hadron Collider, Particle Physics, and Standard Model"),
        ("pubmed.ncbi.nlm.nih.gov", "Biomedical Literature, Genomic Research, and Clinical Trials"),
    ],
    "Encyclopedias & Reference": [
        ("en.wikipedia.org", "The Free Encyclopedia - Science, History, Geography, Culture"),
        ("britannica.com", "Encyclopaedia Britannica - Peer-Reviewed Knowledge Articles"),
        ("gutenberg.org", "Project Gutenberg - Free Classical Literature and Historical Books"),
        ("archive.org", "Internet Archive - Digital Wayback Machine and Public Domain Works"),
    ],
    "Business, News & Economics": [
        ("news.ycombinator.com", "Hacker News - Technology, Startups, and Computer Science"),
        ("reuters.com", "Global Markets, Geopolitics, Financial News, and Breaking Reports"),
        ("bloomberg.com", "Financial Markets, Commodities, Monetary Policy, and Economics"),
        ("economist.com", "Global Economic Analysis, Trade Agreements, and Macroeconomics"),
    ],
    "Mathematics & Theory": [
        ("mathworld.wolfram.com", "Wolfram MathWorld - Number Theory, Differential Geometry, Topology"),
        ("plato.stanford.edu", "Stanford Encyclopedia of Philosophy - Logic, Epistemology, Ethics"),
    ],
}


class CommonCrawlStreamer:
    """
    Streamer and extractor for Common Crawl WET archives and multi-domain partitions.
    """

    def __init__(self, archives_dir: Optional[str] = None):
        self.archives_dir = Path(archives_dir) if archives_dir else Path("data/archives")
        self.archives_dir.mkdir(parents=True, exist_ok=True)

    def parse_wet_stream(self, file_path: str) -> Generator[Dict[str, Any], None, None]:
        """
        Parses Common Crawl WET (WARC Encapsulated Text) format files.
        WET format consists of:
          WARC/1.0
          WARC-Type: conversion
          WARC-Target-URI: http://...
          WARC-Date: 2026-...
          Content-Length: ...
          [Blank line]
          [Extracted plain text]
        """
        p = Path(file_path)
        opener = gzip.open(p, "rt", encoding="utf-8", errors="replace") if p.suffix == ".gz" else open(p, "r", encoding="utf-8", errors="replace")

        current_headers: Dict[str, str] = {}
        content_lines: List[str] = []
        in_header = True

        with opener as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("WARC/1.0"):
                    if current_headers.get("WARC-Target-URI") and content_lines:
                        doc = self._build_document_from_warc(current_headers, "".join(content_lines))
                        if doc:
                            yield doc
                    current_headers = {}
                    content_lines = []
                    in_header = True
                    continue

                if in_header:
                    if not stripped:
                        in_header = False
                        continue
                    if ":" in line:
                        k, v = line.split(":", 1)
                        current_headers[k.strip()] = v.strip()
                else:
                    content_lines.append(line)

            if current_headers.get("WARC-Target-URI") and content_lines:
                doc = self._build_document_from_warc(current_headers, "".join(content_lines))
                if doc:
                    yield doc

    def _build_document_from_warc(self, headers: Dict[str, str], raw_text: str) -> Optional[Dict[str, Any]]:
        target_uri = headers.get("WARC-Target-URI", "")
        if not target_uri or not target_uri.startswith("http"):
            return None

        canonical = normalize_url(target_uri)
        doc_id = compute_url_id(canonical)
        parsed = urlparse(canonical)
        domain = parsed.netloc.lower()

        # Clean text
        text_clean = raw_text.strip()
        if len(text_clean) < 50:
            return None

        first_line = text_clean.split("\n", 1)[0].strip()
        title = first_line[:120] if len(first_line) > 5 else f"Document from {domain}"
        snippet = generate_snippet(text_clean, title, max_length=160)

        return {
            "id": doc_id,
            "url": target_uri,
            "canonical_url": canonical,
            "domain": domain,
            "title": title,
            "snippet": snippet,
            "content": text_clean,
            "language": "en",
            "document_type": "archive_webpage",
            "published_at": headers.get("WARC-Date"),
            "indexed_at": datetime.now(timezone.utc).isoformat(),
            "pagerank": 1.0,
        }

    def write_partition_chunk(self, partition_index: int, documents: List[Dict[str, Any]]) -> Path:
        """Writes a batch of documents into a partitioned JSONL file in data/archives/."""
        out_path = self.archives_dir / f"partition_{partition_index:04d}.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for doc in documents:
                f.write(json.dumps(doc) + "\n")
        logger.info("Wrote partition %s with %d documents.", out_path.name, len(documents))
        return out_path
