import { ExternalLink, Star, Github, CheckCircle, Target } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Repository } from "@/lib/api";
import { useState } from "react";

interface PaperResourcesProps {
  repositories?: Repository[];
}

const PaperResources = ({ repositories = [] }: PaperResourcesProps) => {
  const [showAllRepositories, setShowAllRepositories] = useState(false);

  // Ensure repositories is always an array and filter to show only official repositories
  const safeRepositories = repositories || [];
  const officialRepositories = safeRepositories.filter(repo => repo.is_official);

  const formatStars = (stars: number) => {
    if (stars >= 1000) {
      return `${(stars / 1000).toFixed(1)}k`;
    }
    return stars.toString();
  };

  const getRepositoryDisplayName = (repo: Repository) => {
    if (repo.owner && repo.name) {
      return `${repo.owner}/${repo.name}`;
    }
    // Extract owner/name from URL if not provided
    const match = repo.url.match(/github\.com\/([^/]+)\/([^/]+)/);
    if (match) {
      return `${match[1]}/${match[2]}`;
    }
    return repo.url;
  };


  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
      {/* Code Section */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg flex items-center space-x-2">
            <Github className="w-5 h-5" />
            <span>Code</span>
            <Badge variant="secondary" className="ml-2">
              {officialRepositories.length}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {officialRepositories.length > 0 ? (
            <>
              {(showAllRepositories ? officialRepositories : officialRepositories.slice(0, 5)).map((repo) => (
                <div key={repo.id} className="flex items-center justify-between p-2 bg-muted/30 rounded-lg hover:bg-muted/50 transition-colors">
                  <div className="flex items-center space-x-3 flex-1 min-w-0">
                    <Github className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center space-x-2">
                        <a
                          href={repo.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-paper-blue hover:underline font-medium truncate"
                        >
                          {getRepositoryDisplayName(repo)}
                        </a>
                        {repo.is_official && (
                          <CheckCircle className="w-4 h-4 text-green-600" />
                        )}
                      </div>
                      <div className="flex items-center space-x-2 mt-1">
                        <div className="flex items-center space-x-1 text-sm text-muted-foreground">
                          <Star className="w-3 h-3" />
                          <span>{formatStars(repo.num_stars)}</span>
                        </div>
                        <a
                          href={repo.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                        >
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
              {officialRepositories.length > 5 && (
                <div className="text-center pt-2">
                  <button
                    onClick={() => setShowAllRepositories(!showAllRepositories)}
                    className="text-sm text-paper-blue hover:underline"
                  >
                    {showAllRepositories
                      ? `Show less`
                      : `See all ${officialRepositories.length} implementations`
                    }
                  </button>
                </div>
              )}
            </>
          ) : (
            <div className="text-center py-4 text-muted-foreground">
              <Github className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-xs">No official code implementations available</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Tasks Section */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg flex items-center space-x-2">
            <Target className="w-5 h-5" />
            <span>Tasks</span>
            <Badge variant="secondary" className="ml-2">
              0
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="text-center py-4 text-muted-foreground">
            <Target className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p className="text-xs">Tasks will be available soon</p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default PaperResources;
