export interface SearchResultItem {
  id: string;
  url: string;
  canonical_url: string;
  domain: string;
  title: string;
  snippet: string;
  language: string;
  published_at?: string;
  fetched_at?: string;
  indexed_at?: string;
  score: number;
  document_type: string;
  highlights: string[];
  explanation?: string[];
  features?: Record<string, number>;
}

export interface SearchResponse {
  query: string;
  total: number;
  page: number;
  size: number;
  total_pages: number;
  took_ms: number;
  results: SearchResultItem[];
  is_early_index: boolean;
  message?: string;
}

export interface SuggestionsResponse {
  query: string;
  suggestions: string[];
}

export interface SearchStats {
  total_documents: number;
  index_name: string;
  index_alias: string;
  status: string;
  domains_count: number;
  top_domains: { domain: string; doc_count: number }[];
  storage_bytes?: number;
  live_crawled_count?: number;
  cloud_archived_count?: number;
  cloud_storage_formatted?: string;
}
