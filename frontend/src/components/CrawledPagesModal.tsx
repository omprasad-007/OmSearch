import React, { useState, useEffect } from 'react';
import { fetchCrawledPages } from '../api';
import type { CrawledPageItem } from '../types';

interface CrawledPagesModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectQuery?: (query: string) => void;
}

export const CrawledPagesModal: React.FC<CrawledPagesModalProps> = ({
  isOpen,
  onClose,
  onSelectQuery,
}) => {
  const [pages, setPages] = useState<CrawledPageItem[]>([]);
  const [total, setTotal] = useState<number>(13578);
  const [page, setPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [loading, setLoading] = useState<boolean>(false);
  const [selectedDomain, setSelectedDomain] = useState<string>('');
  const [filterQuery, setFilterQuery] = useState<string>('');
  const [topDomains, setTopDomains] = useState<{ domain: string; count: number }[]>([]);

  useEffect(() => {
    if (!isOpen) return;
    loadPages(page, selectedDomain, filterQuery);
  }, [isOpen, page, selectedDomain]);

  const loadPages = async (p: number, domain: string, q: string) => {
    setLoading(true);
    try {
      const data = await fetchCrawledPages(p, 15, domain || undefined, q || undefined);
      setPages(data.items || []);
      setTotal(data.total || 0);
      setTotalPages(data.total_pages || 1);
      if (data.top_domains && data.top_domains.length > 0) {
        setTopDomains(data.top_domains);
      }
    } catch (err) {
      console.error('Error fetching crawled pages:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    loadPages(1, selectedDomain, filterQuery);
  };

  const handleDomainFilter = (domain: string) => {
    setSelectedDomain(domain === selectedDomain ? '' : domain);
    setPage(1);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm animate-in fade-in duration-200">
      <div
        className="bg-white rounded-2xl max-w-4xl w-full max-h-[90vh] flex flex-col shadow-2xl border border-[#e4e2dd] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-5 border-b border-[#e4e2dd] bg-[#fbf9f5] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-[#37654d]/10 flex items-center justify-center text-[#37654d]">
              <span className="material-symbols-outlined text-[20px]">travel_explore</span>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="font-['Newsreader',serif] text-[20px] font-semibold text-[#1b1c1a]">
                  Live Crawled Web Index
                </h2>
                <span className="px-2 py-0.5 rounded-full text-[11px] font-mono font-semibold bg-[#37654d]/15 text-[#37654d]">
                  {total.toLocaleString()} Verified Pages
                </span>
              </div>
              <p className="text-[12px] text-[#5e5f5b]">
                Real-world web pages discovered by OM Search crawler across 1,061+ domains
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-[#5e5f5b] hover:text-[#1b1c1a] hover:bg-[#efeeea] transition-colors border-none bg-transparent cursor-pointer"
            aria-label="Close"
          >
            <span className="material-symbols-outlined text-[20px]">close</span>
          </button>
        </div>

        {/* Filter and Search Bar */}
        <div className="px-6 py-3 border-b border-[#e4e2dd] bg-white space-y-3">
          <form onSubmit={handleSearchSubmit} className="flex gap-2">
            <div className="relative flex-1 flex items-center bg-[#f5f3f0] rounded-xl px-3 py-1.5 border border-[#e4e2dd] focus-within:border-[#1b1c1a]">
              <span className="material-symbols-outlined text-[#5e5f5b] text-[18px] mr-2">search</span>
              <input
                type="text"
                placeholder="Search crawled URLs, page titles, or keywords…"
                value={filterQuery}
                onChange={(e) => setFilterQuery(e.target.value)}
                className="w-full bg-transparent text-[13px] text-[#1b1c1a] focus:outline-none"
              />
              {filterQuery && (
                <button
                  type="button"
                  onClick={() => {
                    setFilterQuery('');
                    setPage(1);
                    loadPages(1, selectedDomain, '');
                  }}
                  className="text-[#5e5f5b] hover:text-[#1b1c1a] border-none bg-transparent cursor-pointer p-0 mr-1"
                >
                  <span className="material-symbols-outlined text-[16px]">close</span>
                </button>
              )}
            </div>
            <button
              type="submit"
              className="px-4 py-1.5 rounded-xl bg-[#1b1c1a] text-white text-[13px] font-medium hover:bg-[#a03b14] transition-colors border-none cursor-pointer shrink-0"
            >
              Filter
            </button>
          </form>

          {/* Top Domain Pills */}
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-[12px] scrollbar-thin">
            <span className="text-[#5e5f5b] text-[11px] font-medium uppercase tracking-wider shrink-0 mr-1">
              Filter Domain:
            </span>
            <button
              type="button"
              onClick={() => handleDomainFilter('')}
              className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors border cursor-pointer shrink-0 ${
                selectedDomain === ''
                  ? 'bg-[#1b1c1a] text-white border-[#1b1c1a]'
                  : 'bg-[#f5f3f0] text-[#57423b] border-[#e4e2dd] hover:bg-[#efeeea]'
              }`}
            >
              All Domains
            </button>
            {topDomains.slice(0, 10).map((d) => (
              <button
                key={d.domain}
                type="button"
                onClick={() => handleDomainFilter(d.domain)}
                className={`px-2.5 py-1 rounded-lg text-[11px] font-mono transition-colors border cursor-pointer shrink-0 ${
                  selectedDomain === d.domain
                    ? 'bg-[#37654d] text-white border-[#37654d]'
                    : 'bg-[#f5f3f0] text-[#57423b] border-[#e4e2dd] hover:bg-[#efeeea]'
                }`}
              >
                {d.domain} <span className="opacity-70 font-sans">({d.count})</span>
              </button>
            ))}
          </div>
        </div>

        {/* Content List */}
        <div className="flex-1 overflow-y-auto p-6 space-y-3 bg-[#fbf9f5]/50">
          {loading ? (
            <div className="py-16 text-center text-[#5e5f5b] flex flex-col items-center justify-center gap-3">
              <span className="material-symbols-outlined text-[32px] animate-spin text-[#37654d]">
                progress_activity
              </span>
              <span className="text-[14px]">Loading crawled pages from index…</span>
            </div>
          ) : pages.length === 0 ? (
            <div className="py-16 text-center text-[#5e5f5b]">
              <span className="material-symbols-outlined text-[36px] mb-2 opacity-50">search_off</span>
              <p className="text-[14px]">No crawled pages found matching your filters.</p>
              <button
                onClick={() => {
                  setSelectedDomain('');
                  setFilterQuery('');
                  setPage(1);
                  loadPages(1, '', '');
                }}
                className="mt-3 px-3 py-1.5 rounded-lg text-[12px] bg-[#efeeea] text-[#1b1c1a] border-none cursor-pointer hover:bg-[#e4e2dd]"
              >
                Reset Filters
              </button>
            </div>
          ) : (
            pages.map((p) => (
              <div
                key={p.id}
                className="p-4 rounded-xl bg-white border border-[#e4e2dd] hover:border-[#cfcdcc] hover:shadow-sm transition-all flex flex-col gap-2 group"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-[#37654d]/10 text-[#37654d]">
                        <span className="w-1.5 h-1.5 rounded-full bg-[#37654d]" />
                        Live Crawled
                      </span>
                      <span className="font-mono text-[11px] text-[#5e5f5b] truncate max-w-[280px]">
                        {p.domain}
                      </span>
                      {p.indexed_at && (
                        <span className="text-[11px] text-[#5e5f5b]/70">
                          · {new Date(p.indexed_at).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                    <a
                      href={p.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-medium text-[15px] text-[#1b1c1a] group-hover:text-[#a03b14] transition-colors leading-snug line-clamp-1 flex items-center gap-1.5"
                    >
                      <span>{p.title}</span>
                      <span className="material-symbols-outlined text-[14px] opacity-40 group-hover:opacity-100 transition-opacity">
                        open_in_new
                      </span>
                    </a>
                  </div>

                  {onSelectQuery && (
                    <button
                      onClick={() => {
                        onSelectQuery(p.title.split(' — ')[0]);
                        onClose();
                      }}
                      className="px-2.5 py-1 rounded-lg text-[11px] font-medium bg-[#f5f3f0] hover:bg-[#a03b14] hover:text-white text-[#57423b] transition-colors border-none cursor-pointer shrink-0 flex items-center gap-1"
                      title="Search this title in OM Search"
                    >
                      <span className="material-symbols-outlined text-[13px]">search</span>
                      <span>Search</span>
                    </button>
                  )}
                </div>

                <p className="text-[12px] text-[#57423b] line-clamp-2 leading-relaxed">
                  {p.snippet}
                </p>

                <div className="text-[11px] font-mono text-[#5e5f5b] truncate">
                  {p.url}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Pagination Footer */}
        <div className="px-6 py-3 border-t border-[#e4e2dd] bg-[#fbf9f5] flex items-center justify-between text-[12px] text-[#5e5f5b]">
          <div>
            Showing Page <span className="font-semibold text-[#1b1c1a]">{page}</span> of{' '}
            <span className="font-semibold text-[#1b1c1a]">{totalPages}</span> ({total.toLocaleString()} total)
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((prev) => Math.max(1, prev - 1))}
              disabled={page <= 1 || loading}
              className="px-3 py-1.5 rounded-lg bg-white border border-[#e4e2dd] text-[#1b1c1a] hover:bg-[#efeeea] disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
            >
              Previous
            </button>
            <button
              onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
              disabled={page >= totalPages || loading}
              className="px-3 py-1.5 rounded-lg bg-white border border-[#e4e2dd] text-[#1b1c1a] hover:bg-[#efeeea] disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
            >
              Next
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
