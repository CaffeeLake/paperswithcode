import { ChevronUp, Github, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Link } from "react-router-dom";

interface Author {
  name: string;
  color: string;
}

interface TrendingPaperCardProps {
  id: string;
  title: string;
  abstract: string;
  authors: Author[];
  submittedBy: string;
  date: string;
  upvotes: number;
  comments: number;
  category: string;
  isUpvoted: boolean;
  githubStars: number;
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
  upvotes,
  isUpvoted,
  githubStars,
}: TrendingPaperCardProps) => {
  return (
    <div className="flex gap-6 p-6 bg-card rounded-lg border hover:shadow-md transition-shadow">
      {/* Paper Preview */}
      <div className="flex-shrink-0 w-48">
        <div className="w-full h-32 bg-muted/50 rounded border flex items-center justify-center text-muted-foreground text-sm">
          Paper Preview
        </div>
        <div className="mt-2 text-xs text-muted-foreground">
          Submitted by <span className="text-primary">@{submittedBy}</span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <Link to={`/paper/${id}`} className="block group">
          <h3 className="text-lg font-semibold text-foreground group-hover:text-primary transition-colors mb-2">
            {title}
          </h3>
        </Link>
        
        <p className="text-sm text-muted-foreground mb-4 leading-relaxed line-clamp-3">
          {abstract}
        </p>

        <div className="flex items-center gap-4 mb-3">
          {/* Authors */}
          <div className="flex items-center gap-2">
            <div className="flex items-center space-x-1">
              {authors.slice(0, 4).map((author, index) => (
                <Avatar key={index} className="w-6 h-6">
                  <AvatarFallback 
                    className="text-xs text-white"
                    style={{ backgroundColor: author.color }}
                  >
                    {author.name.split(' ').map(n => n[0]).join('')}
                  </AvatarFallback>
                </Avatar>
              ))}
              {authors.length > 4 && (
                <span className="text-xs text-muted-foreground ml-1">
                  +{authors.length - 4} authors
                </span>
              )}
            </div>
            <span className="text-xs text-muted-foreground">• Published on {date}</span>
          </div>
        </div>
      </div>

      {/* Right Actions */}
      <div className="flex flex-col items-end gap-3 flex-shrink-0">
        {/* Upvote */}
        <Button
          variant={isUpvoted ? "default" : "outline"}
          size="sm"
          className="flex items-center gap-1"
        >
          <ChevronUp className="w-4 h-4" />
          <span className="text-sm font-medium">Upvote</span>
          <span className="text-sm">{upvotes}</span>
        </Button>

        {/* GitHub Stars */}
        <div className="flex items-center gap-1 text-sm text-muted-foreground">
          <Github className="w-4 h-4" />
          <span className="font-medium">{formatStars(githubStars)}</span>
        </div>

        {/* arXiv Link */}
        <Button variant="outline" size="sm" className="text-xs">
          <ExternalLink className="w-3 h-3 mr-1" />
          arXiv Page
        </Button>
      </div>
    </div>
  );
};

export default TrendingPaperCard;