import { ArrowUp, MessageCircle, Calendar, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { useNavigate } from "react-router-dom";
import PaperThumbnail from "@/components/PaperThumbnail";
import LatexTitle from "@/components/LatexTitle";

interface Author {
  name: string;
  avatar?: string;
  color: string;
}

interface PaperCardProps {
  id: string;
  title: string;
  abstract: string;
  authors: Author[];
  submittedBy: string;
  submittedByAvatar?: string;
  date: string;
  upvotes: number;
  comments: number;
  thumbnail?: string;
  category: string;
  isUpvoted?: boolean;
  githubStars?: number;
}

const PaperCard = ({
  id,
  title,
  abstract,
  authors,
  submittedBy,
  submittedByAvatar,
  date,
  upvotes,
  comments,
  thumbnail,
  category,
  isUpvoted = false,
}: PaperCardProps) => {
  const navigate = useNavigate();

  const handleCardClick = () => {
    navigate(`/paper/${id}`);
  };

  return (
    <Card
      className="group transition-all duration-200 hover:shadow-paper-hover hover:-translate-y-1 cursor-pointer"
      onClick={handleCardClick}
    >
      <CardContent className="p-0">
        {/* Paper Thumbnail */}
        <div className="aspect-[4/3] bg-gradient-card rounded-t-lg border-b">
          <PaperThumbnail
            thumbnailUrl={thumbnail}
            title={title}
            className="w-full h-full p-4"
          />
        </div>

        <div className="p-4">
          {/* Category Badge */}
          <Badge variant="secondary" className="mb-3 text-xs">
            {category}
          </Badge>

          {/* Paper Title */}
          <h3 className="font-semibold text-lg leading-tight mb-2 line-clamp-2 group-hover:text-primary transition-colors">
            <LatexTitle title={title} />
          </h3>

          {/* Authors */}
          <div className="flex items-center space-x-2 mb-3">
            <div className="flex -space-x-2">
              {authors.slice(0, 5).map((author, index) => (
                <Avatar key={index} className="w-6 h-6 border-2 border-background">
                  <AvatarImage src={author.avatar} />
                  <AvatarFallback
                    className="text-xs text-white font-medium"
                    style={{ backgroundColor: author.color }}
                  >
                    {author.name.split(' ').map(n => n[0]).join('').slice(0, 2)}
                  </AvatarFallback>
                </Avatar>
              ))}
            </div>
            <span className="text-sm text-muted-foreground">
              {authors.length} author{authors.length !== 1 ? 's' : ''}
            </span>
            {authors.length > 5 && (
              <span className="text-xs text-muted-foreground">
                +{authors.length - 5} more
              </span>
            )}
          </div>

          {/* Submitted By */}
          <div className="flex items-center space-x-2 mb-4">
            <span className="text-sm text-muted-foreground">Submitted by</span>
            <Avatar className="w-5 h-5">
              <AvatarImage src={submittedByAvatar} />
              <AvatarFallback className="text-xs bg-paper-blue text-white">
                {submittedBy[0]}
              </AvatarFallback>
            </Avatar>
            <span className="text-sm font-medium text-paper-blue">{submittedBy}</span>
          </div>

          {/* Actions */}
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <Button
                variant="ghost"
                size="sm"
                className={`flex items-center space-x-1 h-8 px-2 ${
                  isUpvoted ? 'text-primary bg-primary/10' : 'text-muted-foreground'
                }`}
              >
                <ArrowUp className="w-4 h-4" />
                <span className="text-sm font-medium">{upvotes}</span>
              </Button>
              <Button variant="ghost" size="sm" className="flex items-center space-x-1 h-8 px-2 text-muted-foreground">
                <MessageCircle className="w-4 h-4" />
                <span className="text-sm">{comments}</span>
              </Button>
            </div>
            <div className="flex items-center text-xs text-muted-foreground">
              <Calendar className="w-3 h-3 mr-1" />
              {date}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default PaperCard;
