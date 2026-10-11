from app.ingestion.pipeline import IngestionPipeline


def test_ingestion_and_deduplication():
    pipeline = IngestionPipeline()

    doc1 = {
        "url": "https://omsearch.org/article-1",
        "title": "Search Engine Architecture",
        "content": "A search engine consists of a crawler, indexing engine, document store, and ranking function.",
    }
    res1 = pipeline.process_raw_document(doc1)
    assert res1["status"] == "indexed"

    # Ingest document with exact same content under different URL -> duplicate detection
    doc2 = {
        "url": "https://omsearch.org/article-1-mirror",
        "title": "Search Engine Architecture Copy",
        "content": "A search engine consists of a crawler, indexing engine, document store, and ranking function.",
    }
    res2 = pipeline.process_raw_document(doc2)
    assert res2["status"] == "duplicate"


def test_ingestion_handles_malformed_url_safely():
    pipeline = IngestionPipeline()
    res = pipeline.process_raw_document({"url": "", "title": "Empty"})
    assert res["status"] == "skipped"
