from typing import Dict, Any

OPENSEARCH_INDEX_MAPPING: Dict[str, Any] = {
    "settings": {
        "index": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "refresh_interval": "1s",
        },
        "analysis": {
            "filter": {
                "english_stop": {
                    "type": "stop",
                    "stopwords": "_english_",
                },
                "english_stemmer": {
                    "type": "stemmer",
                    "language": "english",
                },
                "edge_ngram_filter": {
                    "type": "edge_ngram",
                    "min_gram": 2,
                    "max_gram": 15,
                },
            },
            "analyzer": {
                "om_english_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": [
                        "lowercase",
                        "english_stop",
                        "english_stemmer",
                    ],
                },
                "om_suggest_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": [
                        "lowercase",
                        "edge_ngram_filter",
                    ],
                },
            },
        },
    },
    "mappings": {
        "properties": {
            "id": {"type": "keyword"},
            "url": {"type": "keyword"},
            "canonical_url": {"type": "keyword"},
            "domain": {"type": "keyword"},
            "title": {
                "type": "text",
                "analyzer": "standard",
                "fields": {
                    "english": {
                        "type": "text",
                        "analyzer": "om_english_analyzer",
                    },
                    "keyword": {
                        "type": "keyword",
                        "ignore_above": 256,
                    },
                    "suggest": {
                        "type": "text",
                        "analyzer": "om_suggest_analyzer",
                        "search_analyzer": "standard",
                    },
                },
            },
            "content": {
                "type": "text",
                "analyzer": "standard",
                "fields": {
                    "english": {
                        "type": "text",
                        "analyzer": "om_english_analyzer",
                    },
                },
            },
            "snippet": {
                "type": "text",
                "analyzer": "standard",
            },
            "language": {"type": "keyword"},
            "published_at": {
                "type": "date",
                "format": "strict_date_optional_time||epoch_millis",
            },
            "fetched_at": {
                "type": "date",
                "format": "strict_date_optional_time||epoch_millis",
            },
            "indexed_at": {
                "type": "date",
                "format": "strict_date_optional_time||epoch_millis",
            },
            "content_hash": {"type": "keyword"},
            "http_status": {"type": "integer"},
            "document_type": {"type": "keyword"},
        }
    },
}
