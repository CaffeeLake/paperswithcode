import { ExternalLink, Star, Github, CheckCircle, Target, Zap } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Repository } from "@/lib/api";
import { useState } from "react";
import { Link } from "react-router-dom";

interface Task {
  id: string;
  name: string;
  slug?: string;
}

interface Method {
  id: string;
  name: string;
  source_url?: string;
  source_title?: string;
  code_snippet_url?: string;
}

interface PaperResourcesProps {
  repositories?: Repository[];
  tasks?: Task[];
  methods?: Method[];
}

const PaperResources = ({ repositories = [], tasks = [], methods = [] }: PaperResourcesProps) => {
  const [showAllRepositories, setShowAllRepositories] = useState(false);

  // Ensure repositories is always an array and filter to show official and high-quality repositories
  const safeRepositories = repositories || [];
  const displayRepositories = safeRepositories.filter(repo =>
    repo.is_official || repo.num_stars >= 100
  ).sort((a, b) => {
    // Sort by official status first, then by stars
    if (a.is_official && !b.is_official) return -1;
    if (!a.is_official && b.is_official) return 1;
    return b.num_stars - a.num_stars;
  });

  const formatStars = (stars: number) => {
    if (stars >= 1000) {
      return `${(stars / 1000).toFixed(1)}k`;
    }
    return stars.toString();
  };

  const getRepositoryDisplayName = (repo: Repository) => {
    // Check if there are multiple repositories with the same owner/name
    const sameOwnerRepos = displayRepositories.filter(r =>
      r.owner === repo.owner && r.name === repo.name
    );

    // If there are multiple repos from the same owner/name, show the full URL path
    if (sameOwnerRepos.length > 1) {
      // For GitHub URLs with subdirectories, show the path after the repo name
      const match = repo.url.match(/github\.com\/([^/]+)\/([^/]+)(?:\/tree\/master\/(.+))?/);
      if (match) {
        const [, owner, name, subPath] = match;
        if (subPath) {
          return `${owner}/${name}/${subPath}`;
        }
        return `${owner}/${name}`;
      }
      // Fallback to full URL if pattern doesn't match
      return repo.url;
    }

    // For single repositories, use the standard owner/name format
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
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
      {/* Code Section */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg flex items-center space-x-2">
            <Github className="w-5 h-5" />
            <span>Code</span>
            <Badge variant="secondary" className="ml-2">
              {displayRepositories.length}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {displayRepositories.length > 0 ? (
            <>
              {(showAllRepositories ? displayRepositories : displayRepositories.slice(0, 5)).map((repo) => (
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
              {displayRepositories.length > 5 && (
                <div className="text-center pt-2">
                  <button
                    onClick={() => setShowAllRepositories(!showAllRepositories)}
                    className="text-sm text-paper-blue hover:underline"
                  >
                    {showAllRepositories
                      ? `Show less`
                      : `See all ${displayRepositories.length} implementations`
                    }
                  </button>
                </div>
              )}
            </>
          ) : (
            <div className="text-center py-4 text-muted-foreground">
              <Github className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-xs">No code implementations available</p>
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
              {tasks.length}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {tasks.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {tasks.map((task: Task) => (
                <Link key={task.id} to={`/tasks/${task.slug || task.name.toLowerCase().replace(/\s+/g, '-')}`}>
                  <Badge variant="secondary" className="text-sm hover:bg-secondary/80 cursor-pointer transition-colors">
                    {task.name}
                  </Badge>
                </Link>
              ))}
            </div>
          ) : (
            <div className="text-center py-4 text-muted-foreground">
              <Target className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-xs">No tasks available</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Methods Section */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg flex items-center space-x-2">
            <Zap className="w-5 h-5" />
            <span>Methods</span>
            <Badge variant="secondary" className="ml-2">
              {methods.length}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {methods.length > 0 ? (
            <div className="space-y-3">
              {methods.map((method: Method) => (
                <div key={method.id} className="p-3 bg-muted/30 rounded-lg hover:bg-muted/50 transition-colors">
                  <Link to={`/methods/${method.id}`}>
                    <h3 className="font-medium text-sm mb-2 hover:text-primary transition-colors">
                      {method.name}
                    </h3>
                  </Link>
                  {(method.source_url || method.code_snippet_url) && (
                    <div className="flex gap-2 mt-2">
                      {method.source_url && (
                        <a
                          href={method.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 px-3 py-1 text-xs bg-primary text-primary-foreground rounded hover:bg-primary/90 transition-colors"
                          onClick={(e) => e.stopPropagation()}
                        >
                          Read paper
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                      {method.code_snippet_url && (
                        <a
                          href={method.code_snippet_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 px-3 py-1 text-xs bg-secondary text-secondary-foreground rounded hover:bg-secondary/90 transition-colors"
                          onClick={(e) => e.stopPropagation()}
                        >
                          See code
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-4 text-muted-foreground">
              <Zap className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-xs">No methods available</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default PaperResources;
