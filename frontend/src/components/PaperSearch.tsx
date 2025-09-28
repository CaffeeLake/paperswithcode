import { useState, useEffect, useRef } from "react";
import { Search, Loader2, ExternalLink } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useNavigate } from "react-router-dom";

interface PaperSummary {
  id: string;
  title: string;
  authors: string[];
  citation_count: number;
  published: string;
  arxiv_id?: string;
}

export function PaperSearch() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PaperSummary[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showResults, setShowResults] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const searchRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  // Debounce search
  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      setShowResults(false);
      return;
    }

    const timer = setTimeout(async () => {
      setIsLoading(true);
      setError(null);

      try {
        const response = await fetch(
          `http://167.235.148.241:8000/api/v1/papers/search?q=${encodeURIComponent(query)}&limit=5`
        );

        if (!response.ok) {
          throw new Error('Search failed');
        }

        const data = await response.json();
        setResults(data);
        setShowResults(true);
      } catch (err) {
        setError('Search failed');
        setResults([]);
      } finally {
        setIsLoading(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [query]);

  // Close results when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (searchRef.current && !searchRef.current.contains(event.target as Node)) {
        setShowResults(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      navigate(`/papers?search=${encodeURIComponent(query)}`);
      setShowResults(false);
    }
  };

  const handleResultClick = (paper: PaperSummary) => {
    // Use arxiv_id if available, otherwise fall back to id
    const urlParam = paper.arxiv_id || paper.id;
    navigate(`/paper/${urlParam}`);
    setShowResults(false);
    setQuery("");
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).getFullYear().toString();
  };

  return (
    <div ref={searchRef} className="relative flex-1 max-w-md mx-8">
      <form onSubmit={handleSubmit}>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-4 h-4" />
          <Input
            className="pl-10 pr-10 bg-muted/50 border-0 focus-visible:ring-1 focus-visible:ring-primary"
            placeholder="Search papers..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => query && setShowResults(true)}
          />
          {isLoading && (
            <Loader2 className="absolute right-3 top-1/2 transform -translate-y-1/2 w-4 h-4 animate-spin text-muted-foreground" />
          )}
        </div>
      </form>

      {/* Search Results Dropdown */}
      {showResults && (query.trim() || error) && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-background border border-border rounded-md shadow-lg z-50 max-h-96 overflow-y-auto">
          {error ? (
            <div className="p-4 text-center text-red-500 text-sm">
              {error}
            </div>
          ) : results.length > 0 ? (
            <>
              {results.map((paper) => (
                <button
                  key={paper.id}
                  onClick={() => handleResultClick(paper)}
                  className="w-full p-3 text-left hover:bg-muted/50 border-b border-border last:border-b-0 transition-colors"
                >
                  <div className="font-medium text-sm line-clamp-2 mb-1">
                    {paper.title}
                  </div>
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <div className="flex items-center space-x-2">
                      {paper.authors.length > 0 && (
                        <span>{paper.authors.slice(0, 2).join(", ")}{paper.authors.length > 2 ? " et al." : ""}</span>
                      )}
                      <span>•</span>
                      <span>{formatDate(paper.published)}</span>
                    </div>
                    <div className="flex items-center space-x-2">
                      <span>{paper.citation_count} citations</span>
                      {paper.arxiv_id && (
                        <ExternalLink className="w-3 h-3" />
                      )}
                    </div>
                  </div>
                </button>
              ))}
              <div className="p-2 border-t border-border">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    navigate(`/papers?search=${encodeURIComponent(query)}`);
                    setShowResults(false);
                  }}
                  className="w-full text-xs"
                >
                  View all results for "{query}"
                </Button>
              </div>
            </>
          ) : (
            <div className="p-4 text-center text-muted-foreground text-sm">
              No papers found for "{query}"
            </div>
          )}
        </div>
      )}
    </div>
  );
}
