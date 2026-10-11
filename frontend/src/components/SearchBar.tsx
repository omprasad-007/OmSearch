import React, { useState, useEffect, useRef } from 'react';
import { Search, X, ArrowRight, CornerDownLeft } from 'lucide-react';
import { fetchSuggestions } from '../api';

interface SearchBarProps {
  initialValue?: string;
  onSearch: (query: string) => void;
  autoFocus?: boolean;
  placeholder?: string;
}

export const SearchBar: React.FC<SearchBarProps> = ({
  initialValue = '',
  onSearch,
  autoFocus = false,
  placeholder = 'Search the web or indexed corpus...',
}) => {
  const [query, setQuery] = useState(initialValue);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState<number>(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setQuery(initialValue);
  }, [initialValue]);

  // Fetch suggestions with debounce
  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }

    const timer = setTimeout(async () => {
      const items = await fetchSuggestions(trimmed);
      setSuggestions(items);
      setShowSuggestions(items.length > 0);
      setSelectedIndex(-1);
    }, 180);

    return () => clearTimeout(timer);
  }, [query]);

  // Click outside listener
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const finalQuery = selectedIndex >= 0 && suggestions[selectedIndex]
      ? suggestions[selectedIndex]
      : query;

    if (finalQuery.trim()) {
      setShowSuggestions(false);
      onSearch(finalQuery.trim());
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!showSuggestions || suggestions.length === 0) {
      if (e.key === 'Enter') {
        handleSubmit();
      }
      return;
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev < suggestions.length - 1 ? prev + 1 : 0));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev > 0 ? prev - 1 : suggestions.length - 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      handleSubmit();
    } else if (e.key === 'Escape') {
      setShowSuggestions(false);
    }
  };

  const handleSelectSuggestion = (item: string) => {
    setQuery(item);
    setShowSuggestions(false);
    onSearch(item);
  };

  return (
    <div className="search-box-wrapper" ref={containerRef}>
      <form onSubmit={handleSubmit} className="search-box" role="search">
        <span className="search-icon">
          <Search size={20} />
        </span>
        <input
          ref={inputRef}
          type="text"
          className="search-input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => query.trim().length >= 2 && suggestions.length > 0 && setShowSuggestions(true)}
          placeholder={placeholder}
          autoFocus={autoFocus}
          autoComplete="off"
          spellCheck="false"
          aria-label="Search query"
        />
        {query && (
          <button
            type="button"
            className="clear-btn"
            onClick={() => {
              setQuery('');
              setSuggestions([]);
              setShowSuggestions(false);
              inputRef.current?.focus();
            }}
            aria-label="Clear query"
          >
            <X size={18} />
          </button>
        )}
        <button type="submit" className="submit-btn" aria-label="Submit search">
          <span>Search</span>
          <CornerDownLeft size={14} />
        </button>
      </form>

      {showSuggestions && suggestions.length > 0 && (
        <ul className="suggestions-dropdown" role="listbox">
          {suggestions.map((item, idx) => (
            <li
              key={idx}
              className={`suggestion-item ${idx === selectedIndex ? 'active' : ''}`}
              onClick={() => handleSelectSuggestion(item)}
              role="option"
              aria-selected={idx === selectedIndex}
            >
              <Search size={16} className="suggestion-icon" />
              <span>{item}</span>
              <ArrowRight size={14} style={{ marginLeft: 'auto', opacity: 0.4 }} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
