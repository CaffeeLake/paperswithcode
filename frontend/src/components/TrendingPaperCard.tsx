import { Star, FileText, Github } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Link } from "react-router-dom";
import PaperThumbnail from "@/components/PaperThumbnail";
import LatexTitle from "@/components/LatexTitle";

interface Author {
  name: string;
  color: string;
}

interface TrendingPaperCardProps {
  id: string;
  title: string;
  abstract: string;
  authors: Author[];
  submittedBy?: string;
  date: string;
  githubStars: number;
  starsPerHour?: number;
  tags: string[];
  thumbnailUrl?: string;
  arxivId?: string;
  githubUrl?: string;
}

const formatStars = (stars: number) => {
  if (stars >= 1000) {
    return `${(stars / 1000).toFixed(1)}k`;
  }
  return stars.toString();
};

const TrendingPaperCard = ({
  id,
  title,
  abstract,
  authors,
  submittedBy,
  date,
  githubStars,
  starsPerHour,
  tags,
  thumbnailUrl,
  arxivId,
  githubUrl,
}: TrendingPaperCardProps) => {
  return (
    <div className="flex flex-col gap-4 p-4 sm:flex-row sm:items-start sm:gap-6 sm:p-6 bg-card rounded-lg border hover:shadow-md transition-shadow">
      {/* Paper Preview */}
      <div className="flex-shrink-0 w-full sm:w-40 lg:w-48">
        <PaperThumbnail
          thumbnailUrl={thumbnailUrl}
          title={title}
          className="w-full h-40 sm:h-32 rounded-md"
        />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <Link to={`/paper/${arxivId || id}`} className="block group mb-2">
          <h3 className="text-base sm:text-lg font-semibold text-foreground group-hover:text-primary transition-colors">
            <LatexTitle title={title} />
          </h3>
        </Link>

        <div className="flex flex-wrap items-center gap-2 mb-3 text-xs text-muted-foreground">
          {submittedBy && (
            <>
              <Github className="w-3 h-3" />
              <a
                href={githubUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-foreground transition-colors"
              >
                {submittedBy}
              </a>
              <span>•</span>
            </>
          )}
          <span>{date}</span>
        </div>

        {/* Tags */}
        {tags.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {tags.slice(0, 4).map((tag, index) => (
              <Link key={index} to={`/tasks/${tag.toLowerCase().replace(/\s+/g, '-')}`}>
                <Badge variant="secondary" className="text-xs hover:bg-secondary/80 cursor-pointer transition-colors bg-gray-100">
                  📊 {tag}
                </Badge>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* Right Section - Stars & Actions */}
      <div className="flex flex-col gap-3 w-full sm:w-[160px]">
        {/* GitHub Stars Box */}
        {githubStars > 0 && (
          <div className="flex flex-col sm:items-center">
            <div className="flex items-center justify-start sm:justify-center bg-background border rounded-lg p-2 w-full sm:w-auto">
              <Star className="w-3 h-3 text-yellow-500 fill-yellow-500 mr-1" />
              <span className="text-base font-semibold">{formatStars(githubStars)}</span>
            </div>
            {starsPerHour !== undefined && (
              <div className="text-xs text-muted-foreground mt-1 text-left sm:text-center">
                {starsPerHour.toFixed(2)} stars / hour
              </div>
            )}
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex flex-col gap-2 w-full">
          {/* Paper Button */}
          {arxivId && (
            <Button
              variant="default"
              size="sm"
              className="w-full bg-cyan-500 hover:bg-cyan-600 text-white"
              asChild
            >
              <Link to={`/paper/${arxivId}`}>
                <FileText className="w-3 h-3 mr-1" />
                Paper
              </Link>
            </Button>
          )}

          {/* Code Button */}
          {githubUrl && (
            <Button
              variant="default"
              size="sm"
              className="w-full bg-blue-500 hover:bg-blue-600 text-white"
              asChild
            >
              <a href={githubUrl} target="_blank" rel="noopener noreferrer">
                <Github className="w-3 h-3 mr-1" />
                Code
              </a>
            </Button>
          )}
        </div>
      </div>
    </div>
  );
};

export default TrendingPaperCard;
