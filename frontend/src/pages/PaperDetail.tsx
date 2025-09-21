import { ArrowUp, MessageCircle, Calendar, ExternalLink, BookOpen, Database, Zap, Bookmark, Trophy, Edit, Loader2, Globe } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Link, useParams } from "react-router-dom";
import Header from "@/components/Header";
import { usePaper } from "@/hooks/usePapers";
import { useHuggingFaceRepos } from "@/hooks/useHuggingFaceRepos";
import PaperResources from "@/components/PaperResources";

const PaperDetail = () => {
  const { id } = useParams<{ id: string }>();
  const { data: paper, isLoading, error } = usePaper(id || "", !!id);
  const { data: hfRepos, isLoading: hfLoading } = useHuggingFaceRepos(paper?.arxiv_id);

  // Generate colors for authors (similar to the original hardcoded approach)
  const getAuthorColor = (index: number) => {
    const colors = ["#3B82F6", "#8B5CF6", "#EF4444", "#10B981", "#F59E0B", "#EC4899", "#06B6D4", "#84CC16", "#F97316"];
    return colors[index % colors.length];
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-4 py-8">
          <div className="flex items-center justify-center min-h-[400px]">
            <div className="flex items-center space-x-2">
              <Loader2 className="w-6 h-6 animate-spin" />
              <span>Loading paper...</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error || !paper) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-4 py-8">
          <div className="flex items-center justify-center min-h-[400px]">
            <div className="text-center">
              <h2 className="text-2xl font-bold mb-2">Paper Not Found</h2>
              <p className="text-muted-foreground mb-4">
                {error?.message || "The requested paper could not be found."}
              </p>
              <Link to="/papers">
                <Button>Browse Papers</Button>
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Format the publication date
  const formatDate = (dateString: string | null) => {
    if (!dateString) return "Unknown";
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  };

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <div className="container mx-auto px-4 py-8">
        {/* Breadcrumb */}
        <div className="flex items-center space-x-2 text-sm text-muted-foreground mb-6">
          <Link to="/papers" className="hover:text-foreground transition-colors">Papers</Link>
          <span>/</span>
          <span className="text-foreground">{paper.arxiv_id || paper.id}</span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
          {/* Main Content */}
          <div className="lg:col-span-3">
            {/* Paper Header */}
            <div className="mb-8">
              <div className="flex items-start justify-between mb-4">
                <h1 className="text-3xl font-bold leading-tight pr-8">{paper.title}</h1>
                <div className="flex items-center space-x-2">
                  <Button
                    variant="outline"
                    className="flex items-center space-x-2 bg-primary/5 border-primary/20 hover:bg-primary/10"
                  >
                    <ArrowUp className="w-4 h-4" />
                    <span>Upvote</span>
                    <span className="font-semibold">{paper.citation_count || 0}</span>
                  </Button>
                  <div className="flex items-center space-x-1">
                    {/* Colorful author avatars */}
                    <div className="flex -space-x-1">
                      {paper.authors.slice(0, 12).map((_, i) => (
                        <div
                          key={i}
                          className="w-6 h-6 rounded-full border-2 border-background"
                          style={{ backgroundColor: getAuthorColor(i) }}
                        />
                      ))}
                    </div>
                    {paper.citation_count > 0 && (
                      <Badge variant="secondary" className="bg-paper-orange/10 text-paper-orange">
                        +{paper.citation_count}
                      </Badge>
                    )}
                  </div>
                </div>
              </div>

              {/* Metadata */}
              <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground mb-6">
                <div className="flex items-center space-x-1">
                  <span>Published on {formatDate(paper.published?.toString() || null)}</span>
                </div>
                {paper.conference && (
                  <div className="flex items-center space-x-1">
                    <span>Conference: {paper.conference}</span>
                  </div>
                )}
                {paper.version && (
                  <div className="flex items-center space-x-1">
                    <span>Version: {paper.version}</span>
                    {paper.is_latest_version && (
                      <Badge variant="secondary" className="text-xs">Latest</Badge>
                    )}
                  </div>
                )}
              </div>

              {/* Authors */}
              <div className="mb-6">
                <span className="text-sm font-semibold text-foreground">Authors: </span>
                <span className="text-sm">
                  {paper.authors.map((author, index) => (
                    <span key={index}>
                      <button className="text-paper-blue hover:underline font-medium">
                        {author}
                      </button>
                      {index < paper.authors.length - 1 && ", "}
                    </span>
                  ))}
                </span>
              </div>

              {/* Tags - Note: tags are not available in the current API, so we'll hide this section for now */}
              {/*
              <div className="mb-6">
                <div className="flex flex-wrap gap-2">
                  {paper.tags?.map((tag, index) => (
                    <Link key={index} to={`/tasks/${tag.toLowerCase().replace(/\s+/g, '-')}`}>
                      <Badge variant="secondary" className="text-xs hover:bg-secondary/80 cursor-pointer transition-colors">
                        {tag}
                      </Badge>
                    </Link>
                  ))}
                </div>
              </div>
              */}
            </div>

            {/* Abstract */}
            <Card className="mb-8">
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <BookOpen className="w-5 h-5" />
                  <span>Abstract</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="prose prose-sm max-w-none">
                  <p className="leading-relaxed whitespace-pre-wrap">{paper.abstract}</p>
                </div>
              </CardContent>
            </Card>

            {/* Actions */}
            <div className="flex items-center space-x-4 mb-12">
              {paper.url_abs && (
                <Button variant="outline" className="flex items-center space-x-2" asChild>
                  <a href={paper.url_abs} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="w-4 h-4" />
                    <span>View on arXiv</span>
                  </a>
                </Button>
              )}
              {paper.url_pdf && (
                <Button variant="outline" className="flex items-center space-x-2" asChild>
                  <a href={paper.url_pdf} target="_blank" rel="noopener noreferrer">
                    <BookOpen className="w-4 h-4" />
                    <span>PDF</span>
                  </a>
                </Button>
              )}
              {paper.conference_url_abs && (
                <Button variant="outline" className="flex items-center space-x-2" asChild>
                  <a href={paper.conference_url_abs} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="w-4 h-4" />
                    <span>Conference page</span>
                  </a>
                </Button>
              )}
              {/* Project Pages */}
              {paper.project_pages && paper.project_pages.length > 0 && (
                paper.project_pages.map((page, index) => (
                  <Button key={page.id} variant="outline" className="flex items-center space-x-2" asChild>
                    <a href={page.url} target="_blank" rel="noopener noreferrer">
                      <Globe className="w-4 h-4" />
                      <span>Project page{paper.project_pages!.length > 1 ? ` ${index + 1}` : ''}</span>
                    </a>
                  </Button>
                ))
              )}
              <Button variant="outline" className="flex items-center space-x-2">
                <Bookmark className="w-4 h-4" />
                <span>Save</span>
              </Button>
            </div>

            {/* Code and Tasks */}
            <PaperResources
              repositories={paper.repositories}
            />

            {/* Evaluation Results */}
            <Card className="mb-8">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-xl font-semibold">Results from the paper</CardTitle>
                  <Button variant="ghost" size="sm" className="flex items-center space-x-1 text-muted-foreground">
                    <Edit className="w-4 h-4" />
                    <span>Edit</span>
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {/* SOTA Badge */}
                <div className="bg-muted/30 rounded-lg p-4 mb-6">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <Trophy className="w-5 h-5 text-yellow-600" />
                      <span className="font-semibold">SOTA for </span>
                      <Link to="/benchmark/wider-face-easy" className="text-primary hover:underline font-semibold">
                        Face Detection on WIDER Face (Easy)
                      </Link>
                    </div>
                    <button className="text-primary text-sm hover:underline">
                      →| Get a GitHub badge
                    </button>
                  </div>
                </div>

                {/* Evaluation Table */}
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="text-left py-3 px-4 font-medium text-muted-foreground">Task</th>
                        <th className="text-left py-3 px-4 font-medium text-muted-foreground">Dataset</th>
                        <th className="text-left py-3 px-4 font-medium text-muted-foreground">Model</th>
                        <th className="text-left py-3 px-4 font-medium text-muted-foreground">Metric name</th>
                        <th className="text-left py-3 px-4 font-medium text-muted-foreground">Metric value</th>
                        <th className="text-left py-3 px-4 font-medium text-muted-foreground">Global rank</th>
                        <th className="text-left py-3 px-4 font-medium text-muted-foreground">Compare</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr className="border-b border-border hover:bg-muted/20">
                        <td className="py-4 px-4">Face Detection</td>
                        <td className="py-4 px-4">FDDB</td>
                        <td className="py-4 px-4 font-medium">DSFD</td>
                        <td className="py-4 px-4">AP</td>
                        <td className="py-4 px-4 font-semibold">0.991</td>
                        <td className="py-4 px-4 font-semibold"># 1</td>
                        <td className="py-4 px-4">
                          <Link to="/benchmark/fddb">
                            <Button size="sm" className="bg-emerald-500 hover:bg-emerald-600 text-white rounded-full px-4">
                              See all
                            </Button>
                          </Link>
                        </td>
                      </tr>
                      <tr className="border-b border-border hover:bg-muted/20">
                        <td className="py-4 px-4">Face Detection</td>
                        <td className="py-4 px-4">WIDER Face (Easy)</td>
                        <td className="py-4 px-4 font-medium">DSFD</td>
                        <td className="py-4 px-4">AP</td>
                        <td className="py-4 px-4 font-semibold">0.960</td>
                        <td className="py-4 px-4 font-semibold"># 1</td>
                        <td className="py-4 px-4">
                          <Link to="/benchmark/wider-face-easy">
                            <Button size="sm" className="bg-emerald-500 hover:bg-emerald-600 text-white rounded-full px-4">
                              See all
                            </Button>
                          </Link>
                        </td>
                      </tr>
                      <tr className="border-b border-border hover:bg-muted/20">
                        <td className="py-4 px-4">Face Detection</td>
                        <td className="py-4 px-4">WIDER Face (Hard)</td>
                        <td className="py-4 px-4 font-medium">DSFD</td>
                        <td className="py-4 px-4">AP</td>
                        <td className="py-4 px-4 font-semibold">0.900</td>
                        <td className="py-4 px-4 font-semibold"># 1</td>
                        <td className="py-4 px-4">
                          <Link to="/benchmark/wider-face-hard">
                            <Button size="sm" className="bg-emerald-500 hover:bg-emerald-600 text-white rounded-full px-4">
                              See all
                            </Button>
                          </Link>
                        </td>
                      </tr>
                      <tr className="hover:bg-muted/20">
                        <td className="py-4 px-4">Face Detection</td>
                        <td className="py-4 px-4">WIDER Face (Medium)</td>
                        <td className="py-4 px-4 font-medium">DSFD</td>
                        <td className="py-4 px-4">AP</td>
                        <td className="py-4 px-4 font-semibold">0.953</td>
                        <td className="py-4 px-4 font-semibold"># 1</td>
                        <td className="py-4 px-4">
                          <Link to="/benchmark/wider-face-medium">
                            <Button size="sm" className="bg-emerald-500 hover:bg-emerald-600 text-white rounded-full px-4">
                              See all
                            </Button>
                          </Link>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Sidebar */}
          <div className="lg:col-span-1">
            <div className="space-y-6">
              {/* Linked Hugging Face models */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center space-x-2">
                    <Zap className="w-4 h-4" />
                    <span>Linked Hugging Face models</span>
                    {paper.arxiv_id && (
                      <a
                        href={`https://huggingface.co/models?other=arxiv:${paper.arxiv_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="hover:opacity-80 transition-opacity"
                      >
                        <Badge variant="secondary">
                          {hfLoading ? '...' :
                           (hfRepos?.models !== undefined ?
                            (hfRepos.isLimited ? `${hfRepos.models}+` : hfRepos.models) :
                            0
                           )
                          }
                        </Badge>
                      </a>
                    )}
                    {!paper.arxiv_id && <Badge variant="secondary">0</Badge>}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    {hfLoading ? 'Loading...' :
                     (hfRepos?.models ?
                      `${hfRepos.isLimited ? `${hfRepos.models}+` : hfRepos.models} model${hfRepos.models !== 1 ? 's' : ''} linking this paper` :
                      'No model linking this paper'
                     )
                    }
                  </p>
                  {paper.arxiv_id && (
                    <p className="text-xs text-muted-foreground mt-2">
                      Cite arxiv.org/abs/{paper.arxiv_id} in a model README.md to link it to this page.
                    </p>
                  )}
                </CardContent>
              </Card>

              {/* Linked Hugging Face datasets */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center space-x-2">
                    <Database className="w-4 h-4" />
                    <span>Linked Hugging Face datasets</span>
                    {paper.arxiv_id && (
                      <a
                        href={`https://huggingface.co/datasets?other=arxiv:${paper.arxiv_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="hover:opacity-80 transition-opacity"
                      >
                        <Badge variant="secondary">
                          {hfLoading ? '...' :
                           (hfRepos?.datasets !== undefined ?
                            (hfRepos.isLimited ? `${hfRepos.datasets}+` : hfRepos.datasets) :
                            0
                           )
                          }
                        </Badge>
                      </a>
                    )}
                    {!paper.arxiv_id && <Badge variant="secondary">0</Badge>}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    {hfLoading ? 'Loading...' :
                     (hfRepos?.datasets ?
                      `${hfRepos.isLimited ? `${hfRepos.datasets}+` : hfRepos.datasets} dataset${hfRepos.datasets !== 1 ? 's' : ''} linking this paper` :
                      'No dataset linking this paper'
                     )
                    }
                  </p>
                  {paper.arxiv_id && (
                    <p className="text-xs text-muted-foreground mt-2">
                      Cite arxiv.org/abs/{paper.arxiv_id} in a dataset README.md to link it to this page.
                    </p>
                  )}
                </CardContent>
              </Card>

              {/* Linked Hugging Face Spaces */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center space-x-2">
                    <Zap className="w-4 h-4" />
                    <span>Linked Hugging Face Spaces</span>
                    {paper.arxiv_id && (
                      <a
                        href={`https://huggingface.co/spaces?other=arxiv:${paper.arxiv_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="hover:opacity-80 transition-opacity"
                      >
                        <Badge variant="secondary">
                          {hfLoading ? '...' :
                           (hfRepos?.spaces !== undefined ?
                            (hfRepos.isLimited ? `${hfRepos.spaces}+` : hfRepos.spaces) :
                            0
                           )
                          }
                        </Badge>
                      </a>
                    )}
                    {!paper.arxiv_id && <Badge variant="secondary">0</Badge>}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    {hfLoading ? 'Loading..' :
                     (hfRepos?.spaces ?
                      `${hfRepos.isLimited ? `${hfRepos.spaces}+` : hfRepos.spaces} Space${hfRepos.spaces !== 1 ? 's' : ''} linking this paper` :
                      'No Space linking this paper'
                     )
                    }
                  </p>
                  {paper.arxiv_id && (
                    <p className="text-xs text-muted-foreground mt-2">
                      Cite arxiv.org/abs/{paper.arxiv_id} in a Space README.md to link it to this page.
                    </p>
                  )}
                </CardContent>
              </Card>

            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PaperDetail;
