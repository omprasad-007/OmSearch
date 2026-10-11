import React, { useState } from 'react';
import { ExternalLink, Copy, Check } from 'lucide-react';
import type { SearchResultItem } from '../types';

interface SearchResultCardProps {
  item: SearchResultItem;
}

export const SearchResultCard: React.FC<SearchResultCardProps> = ({ item }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(item.url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const formattedDate = item.published_at
    ? new Date(item.published_at).toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      })
    : null;

  return (
    <article className="result-card">
      <div className="result-breadcrumb">
        <span className="domain-badge">{item.domain}</span>
        {item.document_type === 'live_web_page' && (
          <span style={{ fontSize: '10px', background: 'rgba(16, 185, 129, 0.12)', color: '#10b981', border: '1px solid rgba(16, 185, 129, 0.25)', padding: '1px 6px', borderRadius: '4px', fontWeight: 600 }}>
            Live Crawled
          </span>
        )}
        <span className="result-url" title={item.url}>{item.url}</span>
        <button
          onClick={handleCopy}
          title="Copy URL"
          style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', display: 'flex' }}
        >
          {copied ? <Check size={14} color="#10b981" /> : <Copy size={14} />}
        </button>
      </div>

      <h2 className="result-title">
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          dangerouslySetInnerHTML={{ __html: item.title }}
        />
      </h2>

      <p
        className="result-snippet"
        dangerouslySetInnerHTML={{ __html: item.snippet }}
      />

      <div className="result-footer">
        {formattedDate && <span>Published {formattedDate}</span>}
        <span className="score-badge">Score: {item.score}</span>
        <span style={{ textTransform: 'uppercase' }}>{item.language}</span>
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          style={{ display: 'inline-flex', alignItems: 'center', gap: '3px', marginLeft: 'auto' }}
        >
          <span>Visit</span>
          <ExternalLink size={12} />
        </a>
      </div>
    </article>
  );
};
