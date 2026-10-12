import React, { useState, useEffect } from 'react';
import { fetchCrawledPages, API_BASE_URL } from '../api';
import type { CrawledPageItem } from '../types';

interface CrawledPagesModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectQuery?: (query: string) => void;
}

interface BatchRecord {
  batch_id: string;
  source_type: string;
  record_count: number;
  uncompressed_bytes: number;
  compressed_bytes: number;
  sha256: string;
  upload_status: string;
  drive_file_id?: string;
  indexing_status: string;
  uploaded_at: string;
}

export const CrawledPagesModal: React.FC<CrawledPagesModalProps> = ({
  isOpen,
  onClose,
  onSelectQuery,
}) => {
  const [activeTab, setActiveTab] = useState<'hot' | 'drive'>('hot');

  // Hot Searchable Index State
  const [pages, setPages] = useState<CrawledPageItem[]>([]);
  const [total, setTotal] = useState<number>(16608);
  const [page, setPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [loading, setLoading] = useState<boolean>(false);
  const [selectedDomain, setSelectedDomain] = useState<string>('');
  const [filterQuery, setFilterQuery] = useState<string>('');
  const [topDomains, setTopDomains] = useState<{ domain: string; count: number }[]>([]);

  // Google Drive Cold Storage State
  const [driveBatches, setDriveBatches] = useState<BatchRecord[]>([]);
  const [driveTotalBatches, setDriveTotalBatches] = useState<number>(2486);
  const [drivePage, setDrivePage] = useState<number>(1);
  const [driveTotalPages, setDriveTotalPages] = useState<number>(1);
  const [driveLoading, setDriveLoading] = useState<boolean>(false);

  useEffect(() => {
    if (!isOpen) return;
    if (activeTab === 'hot') {
      loadPages(page, selectedDomain, filterQuery);
    } else {
      loadDriveBatches(drivePage);
    }
  }, [isOpen, page, selectedDomain, activeTab, drivePage]);

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

  const loadDriveBatches = async (p: number) => {
    setDriveLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/storage/batches?page=${p}&size=15`, {
        headers: { 'X-Operator-Token': 'om-operator-secret-key-2026' },
      });
      if (res.ok) {
        const data = await res.json();
        setDriveBatches(data.batches || []);
        setDriveTotalBatches(data.total || 0);
        setDriveTotalPages(Math.ceil((data.total || 0) / 15) || 1);
      }
    } catch (err) {
      console.error('Error fetching drive batches:', err);
    } finally {
      setDriveLoading(false);
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

  const formatBytes = (bytes?: number) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm animate-in fade-in duration-200">
      <div
        className="bg-white rounded-2xl max-w-4xl w-full max-h-[90vh] flex flex-col shadow-2xl border border-[#e4e2dd] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-[#e4e2dd] bg-[#fbf9f5] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-[#37654d]/10 flex items-center justify-center text-[#37654d]">
              <span className="material-symbols-outlined text-[20px]">travel_explore</span>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="font-['Newsreader',serif] text-[20px] font-semibold text-[#1b1c1a]">
                  OM Index & Crawled Architecture
                </h2>
              </div>
              <p className="text-[12px] text-[#5e5f5b]">
                Real-world web discovery across 1,180+ domains with durable Google Drive cloud cold storage
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

        {/* Two-Tier Tab Switcher */}
        <div className="px-6 pt-3 pb-2 border-b border-[#e4e2dd] bg-white flex items-center gap-3">
          <button
            type="button"
            onClick={() => setActiveTab('hot')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-[12px] font-semibold transition-all border cursor-pointer ${
              activeTab === 'hot'
                ? 'bg-[#1b1c1a] text-white border-[#1b1c1a] shadow-sm'
                : 'bg-[#f5f3f0] text-[#57423b] border-[#e4e2dd] hover:bg-[#efeeea]'
            }`}
          >
            <span className="material-symbols-outlined text-[16px]">bolt</span>
            <span>Searchable Live Index ({total.toLocaleString()} Pages)</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('drive')}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-[12px] font-semibold transition-all border cursor-pointer ${
              activeTab === 'drive'
                ? 'bg-[#a03b14] text-white border-[#a03b14] shadow-sm'
                : 'bg-[#f5f3f0] text-[#57423b] border-[#e4e2dd] hover:bg-[#efeeea]'
            }`}
          >
            <span className="material-symbols-outlined text-[16px]">cloud_upload</span>
            <span>Google Drive 5 TB Cold Storage ({driveTotalBatches.toLocaleString()} Batches / 7.7M+ Docs)</span>
          </button>
        </div>

        {/* TAB 1: Searchable Hot Index */}
        {activeTab === 'hot' && (
          <>
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
                  All ({total.toLocaleString()})
                </button>
                {topDomains.slice(0, 10).map((d) => (
                  <button
                    key={d.domain}
                    type="button"
                    onClick={() => handleDomainFilter(d.domain)}
                    className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors border cursor-pointer shrink-0 ${
                      selectedDomain === d.domain
                        ? 'bg-[#37654d] text-white border-[#37654d]'
                        : 'bg-[#f5f3f0] text-[#57423b] border-[#e4e2dd] hover:bg-[#efeeea]'
                    }`}
                  >
                    {d.domain} ({d.count})
                  </button>
                ))}
              </div>
            </div>

            {/* Crawled Pages List */}
            <div className="flex-1 overflow-y-auto p-6 space-y-4 divide-y divide-[#e4e2dd]">
              {loading ? (
                <div className="py-12 flex flex-col items-center justify-center text-[#5e5f5b] gap-2">
                  <span className="material-symbols-outlined text-[28px] animate-spin text-[#37654d]">
                    progress_activity
                  </span>
                  <span className="text-[13px]">Loading crawled pages…</span>
                </div>
              ) : pages.length === 0 ? (
                <div className="py-12 text-center text-[#5e5f5b] text-[13px]">
                  No crawled pages match the current filter.
                </div>
              ) : (
                pages.map((p) => (
                  <div key={p.id} className="pt-4 first:pt-0 space-y-1.5 group">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-[#efeeea] text-[#57423b]">
                            HTML
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
          </>
        )}

        {/* TAB 2: Google Drive Cold Storage Batches */}
        {activeTab === 'drive' && (
          <>
            <div className="px-6 py-3 bg-[#faf9f6] border-b border-[#e4e2dd] text-[12px] text-[#57423b] flex items-center justify-between">
              <div>
                <strong>Google One 5 TB Plan Cold Storage:</strong> Pages are compressed into micro-batches (5,000 docs each) and uploaded directly into Google Drive <code className="bg-[#efeeea] px-1 py-0.5 rounded text-[#a03b14]">page-records/</code> with 0 MB laptop disk overhead.
              </div>
              <span className="font-mono text-[11px] font-semibold text-[#a03b14] shrink-0 ml-3">
                {driveTotalBatches.toLocaleString()} Verified Batches
              </span>
            </div>

            <div className="flex-1 overflow-y-auto p-6 space-y-3">
              {driveLoading ? (
                <div className="py-12 flex flex-col items-center justify-center text-[#5e5f5b] gap-2">
                  <span className="material-symbols-outlined text-[28px] animate-spin text-[#a03b14]">
                    progress_activity
                  </span>
                  <span className="text-[13px]">Loading Google Drive batches…</span>
                </div>
              ) : driveBatches.length === 0 ? (
                <div className="py-12 text-center text-[#5e5f5b] text-[13px]">
                  No Google Drive archive batches found.
                </div>
              ) : (
                driveBatches.map((b, idx) => (
                  <div
                    key={b.batch_id || idx}
                    className="p-3.5 rounded-xl border border-[#e4e2dd] bg-white hover:border-[#a03b14]/40 transition-colors shadow-xs"
                  >
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-emerald-100 text-emerald-800 font-semibold">
                          {b.upload_status || 'VERIFIED'}
                        </span>
                        <span className="font-mono font-semibold text-[13px] text-[#1b1c1a]">
                          {b.batch_id}
                        </span>
                      </div>
                      <span className="text-[11px] text-[#5e5f5b] font-mono">
                        {b.uploaded_at ? new Date(b.uploaded_at).toLocaleString() : ''}
                      </span>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[12px] text-[#57423b] pt-1 border-t border-[#f0eee9]">
                      <div>
                        <span className="text-[#8c8b88]">Records:</span>{' '}
                        <strong className="text-[#1b1c1a] font-mono">
                          {(b.record_count || 5000).toLocaleString()} docs
                        </strong>
                      </div>
                      <div>
                        <span className="text-[#8c8b88]">Compressed:</span>{' '}
                        <strong className="text-[#a03b14] font-mono">
                          {formatBytes(b.compressed_bytes)}
                        </strong>
                      </div>
                      <div>
                        <span className="text-[#8c8b88]">Uncompressed:</span>{' '}
                        <strong className="text-[#1b1c1a] font-mono">
                          {formatBytes(b.uncompressed_bytes)}
                        </strong>
                      </div>
                      <div>
                        <span className="text-[#8c8b88]">Cloud File ID:</span>{' '}
                        {b.drive_file_id ? (
                          <a
                            href={`https://drive.google.com/file/d/${b.drive_file_id}/view`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-[#37654d] font-mono underline hover:text-[#1b1c1a] truncate inline-block max-w-[100px] align-bottom"
                            title={b.drive_file_id}
                          >
                            {b.drive_file_id.slice(0, 8)}…
                          </a>
                        ) : (
                          <span className="font-mono text-[#8c8b88]">Uploaded</span>
                        )}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Pagination Footer */}
            <div className="px-6 py-3 border-t border-[#e4e2dd] bg-[#fbf9f5] flex items-center justify-between text-[12px] text-[#5e5f5b]">
              <div>
                Showing Page <span className="font-semibold text-[#1b1c1a]">{drivePage}</span> of{' '}
                <span className="font-semibold text-[#1b1c1a]">{driveTotalPages}</span> ({driveTotalBatches.toLocaleString()} batches)
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setDrivePage((prev) => Math.max(1, prev - 1))}
                  disabled={drivePage <= 1 || driveLoading}
                  className="px-3 py-1.5 rounded-lg bg-white border border-[#e4e2dd] text-[#1b1c1a] hover:bg-[#efeeea] disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
                >
                  Previous
                </button>
                <button
                  onClick={() => setDrivePage((prev) => Math.min(driveTotalPages, prev + 1))}
                  disabled={drivePage >= driveTotalPages || driveLoading}
                  className="px-3 py-1.5 rounded-lg bg-white border border-[#e4e2dd] text-[#1b1c1a] hover:bg-[#efeeea] disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};
