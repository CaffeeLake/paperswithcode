import { useState } from "react";
import { FileText, Loader2 } from "lucide-react";

interface PaperThumbnailProps {
  thumbnailUrl?: string;
  title: string;
  className?: string;
}

const PaperThumbnail = ({
  thumbnailUrl,
  title,
  className = "",
}: PaperThumbnailProps) => {
  const [isLoading, setIsLoading] = useState(false);
  const [hasError, setHasError] = useState(false);

  // If we have a thumbnail URL, try to display it
  if (thumbnailUrl && !hasError) {
    return (
      <div className={`relative overflow-hidden rounded ${className}`}>
        {isLoading && (
          <div className="absolute inset-0 bg-muted/50 flex items-center justify-center">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        )}
        <img
          src={thumbnailUrl}
          alt={`Thumbnail for ${title}`}
          className="w-full h-full object-contain"
          onLoad={() => setIsLoading(false)}
          onLoadStart={() => setIsLoading(true)}
          onError={() => {
            setIsLoading(false);
            setHasError(true);
          }}
        />
      </div>
    );
  }

  // Fallback: show paper preview placeholder
  return (
    <div className={`bg-muted/50 rounded border flex flex-col items-center justify-center text-muted-foreground text-sm p-4 ${className}`}>
      <FileText className="w-8 h-8 mb-2" />
      <span className="text-xs text-center">
        {hasError ? "Preview unavailable" : "Paper Preview"}
      </span>
    </div>
  );
};

export default PaperThumbnail;
