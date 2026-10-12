"""
Builds and verifies a list of 100% genuine, HTTP 200 OK authoritative documentation
and encyclopedic pages for OM Search top taxonomy topics.
"""
import httpx
import json
from pathlib import Path

REAL_AUTHORITATIVE_TOPICS = [
    # React
    ("https://react.dev/learn", "Quick Start – React", "React UI library official quick start guide, components, jsx, and props.", "react.dev", "Frontend"),
    ("https://react.dev/reference/react", "React Reference Overview – React", "React core API hooks, useState, useEffect, useContext, and components.", "react.dev", "Frontend"),
    ("https://react.dev/learn/describing-the-ui", "Describing the UI – React", "Learn how to define components, JSX syntax, and rendering in React.", "react.dev", "Frontend"),
    ("https://react.dev/learn/state-a-components-memory", "State: A Component's Memory – React", "Understanding React state management, hooks, and local component memory.", "react.dev", "Frontend"),
    ("https://react.dev/learn/managing-state", "Managing State – React", "How to structure and scale state in React applications.", "react.dev", "Frontend"),
    ("https://react.dev/blog", "React Blog – React", "Latest announcements, releases, and architectural developments from the React team.", "react.dev", "Frontend"),
    
    # FastAPI
    ("https://fastapi.tiangolo.com/", "FastAPI", "FastAPI framework, high performance, easy to learn, fast to code, ready for production.", "fastapi.tiangolo.com", "Backend APIs"),
    ("https://fastapi.tiangolo.com/tutorial/", "Tutorial - User Guide - FastAPI", "Comprehensive tutorial and user guide for building production REST APIs with FastAPI.", "fastapi.tiangolo.com", "Backend APIs"),
    ("https://fastapi.tiangolo.com/features/", "Features - FastAPI", "FastAPI key features including automatic Swagger docs, Pydantic data validation, and async/await.", "fastapi.tiangolo.com", "Backend APIs"),
    ("https://fastapi.tiangolo.com/async/", "Concurrency and async / await - FastAPI", "Deep dive into Python async/await, coroutines, and threadpools in FastAPI.", "fastapi.tiangolo.com", "Backend APIs"),
    ("https://fastapi.tiangolo.com/tutorial/first-steps/", "First Steps - FastAPI", "Creating your first GET endpoint with FastAPI and running with Uvicorn.", "fastapi.tiangolo.com", "Backend APIs"),
    
    # PyTorch & Machine Learning
    ("https://pytorch.org/", "PyTorch", "An open source machine learning framework that accelerates the path from research prototyping to production.", "pytorch.org", "AI Frameworks"),
    ("https://pytorch.org/tutorials/", "PyTorch Tutorials", "Official deep learning and neural network tutorials using PyTorch tensors and CUDA.", "pytorch.org", "AI Frameworks"),
    ("https://en.wikipedia.org/wiki/Machine_learning", "Machine learning - Wikipedia", "Machine learning study of computer algorithms that improve automatically through data and experience.", "en.wikipedia.org", "AI & Science"),
    ("https://en.wikipedia.org/wiki/Artificial_intelligence", "Artificial intelligence - Wikipedia", "Artificial intelligence intelligence demonstrated by machines, synthesizing human cognition and perception.", "en.wikipedia.org", "AI & Science"),
    ("https://en.wikipedia.org/wiki/Deep_learning", "Deep learning - Wikipedia", "Deep learning artificial neural networks with multiple representation layers for speech and vision.", "en.wikipedia.org", "AI & Science"),
    ("https://cloud.google.com/blog/products/ai-machine-learning", "AI & Machine Learning Blog — Google Cloud", "Google Cloud AI research, foundation models, vertex AI, and machine learning infrastructure.", "cloud.google.com", "AI & Science"),

    # Quantum Computing
    ("https://en.wikipedia.org/wiki/Quantum_computing", "Quantum computing - Wikipedia", "Quantum computing computation utilizing quantum mechanics phenomena such as superposition and entanglement.", "en.wikipedia.org", "Quantum & Physics"),
    ("https://en.wikipedia.org/wiki/Quantum_mechanics", "Quantum mechanics - Wikipedia", "Quantum mechanics fundamental theory in physics describing the physical properties of nature at atomic scales.", "en.wikipedia.org", "Quantum & Physics"),
    ("https://blog.google/innovation-and-ai/models-and-research/quantum-computing/", "Quantum Computing — Google Blog", "Google Quantum AI lab discoveries, quantum supremacy, Willow processor, and error correction.", "blog.google", "Quantum & Physics"),
    ("https://en.wikipedia.org/wiki/Qubit", "Qubit - Wikipedia", "Qubit quantum bit, the basic unit of quantum information in quantum computing systems.", "en.wikipedia.org", "Quantum & Physics"),

    # Docker & Containers
    ("https://docs.docker.com/", "Docker Documentation", "Home of Docker documentation, container runtime, Dockerfiles, and compose specifications.", "docs.docker.com", "Cloud & DevOps"),
    ("https://docs.docker.com/get-started/", "Get Started with Docker", "Step-by-step introduction to building, testing, and deploying containerized applications.", "docs.docker.com", "Cloud & DevOps"),
    ("https://docs.docker.com/engine/", "Docker Engine Overview", "Client-server architecture of Docker daemon, containerd runtime, and CLI tools.", "docs.docker.com", "Cloud & DevOps"),
    ("https://en.wikipedia.org/wiki/Docker_(software)", "Docker (software) - Wikipedia", "Docker OS-level virtualization platform delivering software packages in containers.", "en.wikipedia.org", "Cloud & DevOps"),

    # Kubernetes
    ("https://kubernetes.io/", "Kubernetes - Production-Grade Container Orchestration", "Automated container deployment, horizontal pod autoscaling, and declarative management.", "kubernetes.io", "Cloud & DevOps"),
    ("https://kubernetes.io/docs/home/", "Kubernetes Documentation", "Official documentation for Kubernetes clusters, pods, services, ingress, and deployments.", "kubernetes.io", "Cloud & DevOps"),
    ("https://kubernetes.io/docs/concepts/", "Kubernetes Concepts", "Fundamental concepts of Kubernetes architecture, control plane, kubelet, and etcd.", "kubernetes.io", "Cloud & DevOps"),
    ("https://en.wikipedia.org/wiki/Kubernetes", "Kubernetes - Wikipedia", "Kubernetes open-source container orchestration system originally designed by Google.", "en.wikipedia.org", "Cloud & DevOps"),

    # Databases: PostgreSQL & SQLite
    ("https://www.postgresql.org/", "PostgreSQL: The World's Most Advanced Open Source Relational Database", "PostgreSQL ACID relational database, MVCC, foreign keys, and extensible data types.", "postgresql.org", "Databases"),
    ("https://www.postgresql.org/docs/current/index.html", "PostgreSQL Documentation", "Complete official manual for PostgreSQL SQL syntax, performance tuning, and replication.", "postgresql.org", "Databases"),
    ("https://www.postgresql.org/about/", "About PostgreSQL", "History, architectural highlights, and active community behind the PostgreSQL project.", "postgresql.org", "Databases"),
    ("https://www.sqlite.org/index.html", "SQLite Home Page", "SQLite small, fast, self-contained, high-reliability, full-featured SQL database engine.", "sqlite.org", "Databases"),
    ("https://www.sqlite.org/docs.html", "SQLite Documentation", "Official documentation, SQL syntax guide, C/C++ interface, and architecture papers.", "sqlite.org", "Databases"),
    ("https://www.sqlite.org/whentouse.html", "Appropriate Uses For SQLite", "Guidance on choosing SQLite for embedded applications, local caching, and edge services.", "sqlite.org", "Databases"),
    ("https://www.sqlite.org/fts5.html", "SQLite FTS5 Extension", "Full-text search engine 5 module for SQLite, tokenizers, ranking BM25, and queries.", "sqlite.org", "Databases"),
    ("https://www.sqlite.org/wal.html", "Write-Ahead Logging in SQLite", "SQLite WAL mode concurrency, atomic commit, and high-throughput write performance.", "sqlite.org", "Databases"),

    # Rust
    ("https://www.rust-lang.org/", "Rust Programming Language", "Rust empowering everyone to build reliable and efficient software with memory safety.", "rust-lang.org", "Systems"),
    ("https://www.rust-lang.org/learn", "Learn Rust", "Getting started guides, Rust by Example, and interactive tutorials.", "rust-lang.org", "Systems"),
    ("https://doc.rust-lang.org/book/", "The Rust Programming Language - The Rust Book", "The definitive book on Rust ownership, borrowing, lifetimes, traits, and concurrency.", "doc.rust-lang.org", "Systems"),
    ("https://en.wikipedia.org/wiki/Rust_(programming_language)", "Rust (programming language) - Wikipedia", "Rust general-purpose programming language emphasizing performance, type safety, and concurrency.", "en.wikipedia.org", "Systems"),

    # Linux Kernel
    ("https://www.kernel.org/", "The Linux Kernel Archives", "Official distribution point for the Linux operating system kernel sources and patches.", "kernel.org", "Operating Systems"),
    ("https://docs.kernel.org/", "The Linux Kernel Documentation", "Comprehensive documentation for kernel subsystems, drivers, memory management, and syscalls.", "kernel.org", "Operating Systems"),
    ("https://en.wikipedia.org/wiki/Linux_kernel", "Linux kernel - Wikipedia", "Linux kernel monolithic Unix-like operating system kernel created by Linus Torvalds.", "en.wikipedia.org", "Operating Systems"),

    # Web Standards & MDN
    ("https://developer.mozilla.org/en-US/docs/Web/HTML", "HTML: HyperText Markup Language | MDN", "MDN reference for HTML elements, attributes, semantic structuring, and accessibility.", "developer.mozilla.org", "Web Standards"),
    ("https://developer.mozilla.org/en-US/docs/Web/CSS", "CSS: Cascading Style Sheets | MDN", "MDN documentation for modern CSS styling, flexbox, grid, animations, and typography.", "developer.mozilla.org", "Web Standards"),
    ("https://developer.mozilla.org/en-US/docs/Web/JavaScript", "JavaScript | MDN", "MDN documentation for modern JavaScript ECMAScript syntax, promises, and browser APIs.", "developer.mozilla.org", "Web Standards"),
    ("https://developer.mozilla.org/en-US/docs/Web/HTTP", "HTTP | MDN", "MDN reference for HTTP protocol, request headers, status codes, caching, and CORS.", "developer.mozilla.org", "Web Standards"),

    # Search & Information Retrieval
    ("https://en.wikipedia.org/wiki/Information_retrieval", "Information retrieval - Wikipedia", "Information retrieval activity of obtaining information resources relevant to an information need.", "en.wikipedia.org", "Search Engines"),
    ("https://en.wikipedia.org/wiki/Search_engine_indexing", "Search engine indexing - Wikipedia", "Search engine indexing collecting, parsing, and storing data to facilitate fast and accurate search.", "en.wikipedia.org", "Search Engines"),
    ("https://en.wikipedia.org/wiki/Okapi_BM25", "Okapi BM25 - Wikipedia", "Okapi BM25 ranking function used by search engines to estimate the relevance of documents to a search query.", "en.wikipedia.org", "Search Engines"),
    ("https://en.wikipedia.org/wiki/PageRank", "PageRank - Wikipedia", "PageRank algorithm used by Google Search to rank web pages in their search engine results.", "en.wikipedia.org", "Search Engines"),

    # Science, Astronomy & General Knowledge
    ("https://en.wikipedia.org/wiki/James_Webb_Space_Telescope", "James Webb Space Telescope - Wikipedia", "JWST space telescope designed to conduct infrared astronomy and peer into early cosmic epochs.", "en.wikipedia.org", "Astronomy & Space"),
    ("https://en.wikipedia.org/wiki/General_relativity", "General relativity - Wikipedia", "General relativity geometric theory of gravitation published by Albert Einstein in 1915.", "en.wikipedia.org", "Physics"),
    ("https://en.wikipedia.org/wiki/CRISPR", "CRISPR - Wikipedia", "CRISPR family of DNA sequences and CRISPR-Cas9 genome editing molecular tool.", "en.wikipedia.org", "Biomedicine"),
    ("https://en.wikipedia.org/wiki/Macroeconomics", "Macroeconomics - Wikipedia", "Macroeconomics branch of economics dealing with the performance, structure, behavior, and decision-making of an economy.", "en.wikipedia.org", "Economics"),
    ("https://en.wikipedia.org/wiki/Renaissance", "Renaissance - Wikipedia", "Renaissance period in history marking the transition from the Middle Ages to modernity.", "en.wikipedia.org", "History & Philosophy"),
    ("https://en.wikipedia.org/wiki/Silk_Road", "Silk Road - Wikipedia", "Silk Road historical network of Eurasian trade routes active from the Han dynasty to the Ottoman Empire.", "en.wikipedia.org", "History & Philosophy")
]

def verify_all():
    headers = {"User-Agent": "OMSearchBot/1.0 (+https://omsearch.web.app)"}
    with httpx.Client(timeout=10.0, follow_redirects=True, headers=headers) as client:
        verified = []
        for url, title, snippet, domain, cat in REAL_AUTHORITATIVE_TOPICS:
            try:
                resp = client.get(url)
                if resp.status_code == 200:
                    verified.append({
                        "url": str(resp.url),
                        "canonical_url": str(resp.url),
                        "title": title,
                        "snippet": snippet,
                        "domain": domain,
                        "category": cat,
                        "status": 200
                    })
                    print(f"[200 OK] {url}")
                else:
                    print(f"[{resp.status_code}] {url}")
            except Exception as e:
                print(f"[ERR] {url} -> {e}")

        print(f"\nSuccessfully verified {len(verified)} / {len(REAL_AUTHORITATIVE_TOPICS)} URLs!")
        out_path = Path(__file__).resolve().parent / "verified_curated_urls.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(verified, f, indent=2)
        print(f"Saved verified URLs to {out_path}")

if __name__ == "__main__":
    verify_all()
