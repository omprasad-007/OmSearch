import type { SearchResponse, SuggestionsResponse, SearchStats } from './types';

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export async function fetchSearch(
  query: string,
  page: number = 1,
  size: number = 10,
  domain?: string
): Promise<SearchResponse> {
  const params = new URLSearchParams({
    q: query,
    page: page.toString(),
    size: size.toString(),
  });
  if (domain) {
    params.append('domain', domain);
  }

  const response = await fetch(`${API_BASE_URL}/api/v1/search?${params.toString()}`);
  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({ detail: 'Network error' }));
    throw new Error(errorBody.detail || `Search failed with status ${response.status}`);
  }
  return response.json();
}

export async function fetchSuggestions(query: string): Promise<string[]> {
  if (!query.trim()) return [];
  try {
    const params = new URLSearchParams({ q: query, limit: '6' });
    const response = await fetch(`${API_BASE_URL}/api/v1/suggestions?${params.toString()}`);
    if (!response.ok) return [];
    const data: SuggestionsResponse = await response.json();
    return data.suggestions || [];
  } catch {
    return [];
  }
}

export async function fetchStats(): Promise<SearchStats | null> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/search/stats`);
    if (!response.ok) return null;
    return response.json();
  } catch {
    return null;
  }
}
