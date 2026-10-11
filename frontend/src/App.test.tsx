import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import App from './App';
import * as api from './api';

describe('OM Search Frontend', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.history.pushState({}, '', '/');
    // Default mock stats
    vi.spyOn(api, 'fetchStats').mockResolvedValue({
      total_documents: 40,
      index_name: 'om_documents_v1',
      index_alias: 'om_documents',
      status: 'online',
      domains_count: 8,
      top_domains: [{ domain: 'en.wikipedia.org', doc_count: 30 }],
    });
  });

  it('renders OM Search homepage with brand emblem and editorial headline', () => {
    render(<App />);
    expect(screen.getAllByText('OM Search').length).toBeGreaterThan(0);
    expect(screen.getByText(/Find what matters/i)).toBeDefined();
    expect(screen.getByText(/Search the web/i)).toBeDefined();
  });

  it('renders search omnibar and suggestion examples', () => {
    render(<App />);
    const input = screen.getByPlaceholderText(/Search anything on the web/i);
    expect(input).toBeDefined();
    expect(screen.getByText('Quantum mechanics')).toBeDefined();
  });

  it('executes search and displays results on submit', async () => {
    vi.spyOn(api, 'fetchSearch').mockResolvedValue({
      query: 'python',
      total: 1,
      page: 1,
      size: 10,
      total_pages: 1,
      took_ms: 18.0,
      is_early_index: true,
      results: [
        {
          id: 'test1',
          url: 'https://docs.python.org/3/tutorial',
          canonical_url: 'https://docs.python.org/3/tutorial',
          domain: 'docs.python.org',
          title: 'Python Tutorial',
          snippet: 'An informal introduction to Python.',
          language: 'en',
          score: 3.5,
          document_type: 'documentation',
          highlights: [],
        },
      ],
    });

    render(<App />);
    const input = screen.getByPlaceholderText(/Search anything on the web/i);
    fireEvent.change(input, { target: { value: 'python' } });
    fireEvent.submit(input.closest('form')!);

    await waitFor(() => {
      expect(screen.getByText('Python Tutorial')).toBeDefined();
      expect(screen.getByText(/docs.python.org/i)).toBeDefined();
      expect(screen.getByText(/1 results for "python"/i)).toBeDefined();
    });
  });

  it('displays empty state when no documents match query', async () => {
    vi.spyOn(api, 'fetchSearch').mockResolvedValue({
      query: 'nonexistentterm',
      total: 0,
      page: 1,
      size: 10,
      total_pages: 0,
      took_ms: 2.1,
      is_early_index: true,
      results: [],
    });

    render(<App />);
    const input = screen.getByPlaceholderText(/Search anything on the web/i);
    fireEvent.change(input, { target: { value: 'nonexistentterm' } });
    fireEvent.submit(input.closest('form')!);

    await waitFor(() => {
      expect(screen.getByText(/No indexed results found/i)).toBeDefined();
    });
  });
});
