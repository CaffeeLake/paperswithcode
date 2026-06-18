import { ExternalLink, BookOpen, Database, Zap, Bookmark, Globe, Quote, Loader2, FileText, CheckCircle, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Link, useParams } from "react-router-dom";
import Header from "@/components/Header";
import { usePaperByArxivId } from "@/hooks/usePapers";
import { useHuggingFaceRepos } from "@/hooks/useHuggingFaceRepos";
import { useEvaluationsByPaper } from "@/hooks/useEvaluations";
import PaperResources from "@/components/PaperResources";
import { useState } from "react";
import { LatexTitle, LatexText } from "@/components/LatexTitle";
import { usePaperEditState } from "@/hooks/usePaperEditState";
import { EditTasksDialog } from "@/components/paper-detail/EditTasksDialog";
import { EditMethodsDialog } from "@/components/paper-detail/EditMethodsDialog";
import { EditRepositoriesDialog } from "@/components/paper-detail/EditRepositoriesDialog";
import { EditEvaluationsDialog } from "@/components/paper-detail/EditEvaluationsDialog";
import { EvaluationResultsCard } from "@/components/paper-detail/EvaluationResultsCard";
import { indexPaperFromArxiv } from "@/lib/api";

// Type definitions
interface Task {
  id: string;
  name: string;
  slug?: string;
}

const PaperDetail = () => {
  const { arxivId } = useParams<{ arxivId: string }>();
  const { data: paper, isLoading, error, refetch } = usePaperByArxivId(arxivId || "", !!arxivId);
  const { data: hfRepos, isLoading: hfLoading } = useHuggingFaceRepos(paper?.arxiv_id);
  const { data: evaluations, isLoading: evaluationsLoading } = useEvaluationsByPaper(paper?.id, !!paper?.id);

  // Author display state
  const [showAllAuthors, setShowAllAuthors] = useState(false);
  const AUTHOR_DISPLAY_LIMIT = 30;

  // Indexing state
  const [isIndexing, setIsIndexing] = useState(false);
  const [indexingStatus, setIndexingStatus] = useState<'idle' | 'indexing' | 'success' | 'error'>('idle');
  const [indexingError, setIndexingError] = useState<string | null>(null);

  // Admin editing state
  const {
    isEditingTasks,
    setIsEditingTasks,
    isEditingMethods,
    setIsEditingMethods,
    isEditingRepositories,
    setIsEditingRepositories,
    isEditingEvaluations,
    setIsEditingEvaluations,
  } = usePaperEditState();

  const handleIndexPaper = async () => {
    if (!arxivId) return;

    setIsIndexing(true);
    setIndexingStatus('indexing');
    setIndexingError(null);

    try {
      await indexPaperFromArxiv(arxivId);
      setIndexingStatus('success');

      // Reload the page after a brief delay to show the newly indexed paper
      setTimeout(() => {
        refetch();
      }, 1500);
    } catch (err) {
      console.error('Error indexing paper:', err);
      setIndexingStatus('error');

      // Extract error message from response
      let errorMessage = 'Failed to index paper';
      if (err && typeof err === 'object' && 'response' in err) {
        const error = err as { response?: string };
        if (error.response) {
          try {
            const errorData = JSON.parse(error.response);
            errorMessage = errorData.detail || errorMessage;
          } catch {
            errorMessage = error.response;
          }
        }
      } else if (err instanceof Error) {
        errorMessage = err.message;
      }

      setIndexingError(errorMessage);
      setIsIndexing(false);
    }
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
            <div className="text-center max-w-xl">
              {indexingStatus === 'success' ? (
                <div className="space-y-4">
                  <CheckCircle className="w-16 h-16 text-green-500 mx-auto" />
                  <h2 className="text-2xl font-bold mb-2">Paper Indexed Successfully!</h2>
                  <p className="text-muted-foreground mb-4">
                    Reloading page to display the paper...
                  </p>
                  <div className="flex items-center justify-center space-x-2">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span className="text-sm">Loading...</span>
                  </div>
                </div>
              ) : indexingStatus === 'indexing' ? (
                <div className="space-y-4">
                  <Loader2 className="w-16 h-16 animate-spin text-primary mx-auto" />
                  <h2 className="text-2xl font-bold mb-2">Indexing Paper from ArXiv</h2>
                  <p className="text-muted-foreground mb-4">
                    Fetching paper metadata and adding to database...
                  </p>
                  <p className="text-sm text-muted-foreground">
                    This may take a few seconds
                  </p>
                </div>
              ) : (
                <div className="space-y-4">
                  <FileText className="w-16 h-16 text-muted-foreground mx-auto" />
                  <h2 className="text-2xl font-bold mb-2">Paper Not Found</h2>
                  <p className="text-muted-foreground mb-4">
                    This paper hasn't been indexed yet.
                  </p>

                  {arxivId && (
                    <div className="space-y-4">
                      <p className="text-sm text-muted-foreground">
                        ArXiv ID: <span className="font-mono font-semibold">{arxivId}</span>
                      </p>

                      {indexingStatus === 'error' && indexingError && (
                        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
                          <div className="flex items-start space-x-2">
                            <AlertCircle className="w-5 h-5 text-red-500 mt-0.5 flex-shrink-0" />
                            <div className="text-left">
                              <p className="text-sm font-semibold text-red-900">Indexing Failed</p>
                              <p className="text-sm text-red-700 mt-1">{indexingError}</p>
                            </div>
                          </div>
                        </div>
                      )}

                      <Button
                        onClick={handleIndexPaper}
                        disabled={isIndexing}
                        className="space-x-2"
                      >
                        {isIndexing ? (
                          <>
                            <Loader2 className="w-4 h-4 animate-spin" />
                            <span>Indexing...</span>
                          </>
                        ) : (
                          <>
                            <FileText className="w-4 h-4" />
                            <span>Index from ArXiv</span>
                          </>
                        )}
                      </Button>
                    </div>
                  )}

                  <div className="pt-4">
                    <Link to="/papers">
                      <Button variant="outline">Browse Papers</Button>
                    </Link>
                  </div>
                </div>
              )}
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

  // Format proceeding by removing trailing number (e.g., "ICCV 2023 1" -> "ICCV 2023")
  const formatProceeding = (proceeding: string | null | undefined) => {
    if (!proceeding) return null;
    // Remove trailing space and 1-2 digit number (e.g., " 1", " 11")
    // Only matches 1-2 digits to avoid removing years (4 digits)
    return proceeding.replace(/\s+\d{1,2}$/, '');
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
                <h1 className="text-3xl font-bold leading-tight pr-8"><LatexTitle title={paper.title} /></h1>
                <div className="flex items-center space-x-2 px-4 py-2 bg-primary/5 border border-primary/20 rounded-md">
                  <Quote className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm">Citations:</span>
                  <span className="font-semibold">{paper.citation_count || 0}</span>
                </div>
              </div>

              {/* Metadata */}
              <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground mb-6">
                <div className="flex items-center space-x-1">
                  <span>Published on {formatDate(paper.published?.toString() || null)}</span>
                </div>
                {formatProceeding(paper.proceeding) && (
                  <div className="flex items-center space-x-1">
                    <span>Conference: {formatProceeding(paper.proceeding)}</span>
                  </div>
                )}
              </div>

              {/* Authors */}
              <div className="mb-6">
                <span className="text-sm font-semibold text-foreground">Authors: </span>
                <span className="text-sm">
                  {(showAllAuthors ? paper.authors : paper.authors.slice(0, AUTHOR_DISPLAY_LIMIT)).map((author, index) => (
                    <span key={index}>
                      <button className="text-paper-blue hover:underline font-medium">
                        {author}
                      </button>
                      {index < (showAllAuthors ? paper.authors.length : Math.min(AUTHOR_DISPLAY_LIMIT, paper.authors.length)) - 1 && ", "}
                    </span>
                  ))}
                  {paper.authors.length > AUTHOR_DISPLAY_LIMIT && (
                    <button
                      onClick={() => setShowAllAuthors(!showAllAuthors)}
                      className="ml-2 text-paper-blue hover:underline font-medium text-sm"
                    >
                      {showAllAuthors
                        ? "Show less"
                        : `+${paper.authors.length - AUTHOR_DISPLAY_LIMIT} more authors`
                      }
                    </button>
                  )}
                </span>
              </div>
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
                <div className="text-sm">
                  <p className="leading-relaxed text-justify text-foreground">
                    <LatexText text={paper.abstract} />
                  </p>
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

            {/* Code, Tasks, and Methods */}
            <PaperResources
              repositories={paper.repositories || []}
              tasks={paper.tasks || []}
              methods={paper.methods || []}
              onEditTasks={() => setIsEditingTasks(true)}
              onEditMethods={() => setIsEditingMethods(true)}
              onEditRepositories={() => setIsEditingRepositories(true)}
            />

            {/* Evaluation Results */}
            <EvaluationResultsCard
              evaluations={evaluations}
              isLoading={evaluationsLoading}
              onEdit={() => setIsEditingEvaluations(true)}
            />
          </div>

          {/* Sidebar */}
          <div className="lg:col-span-1">
            <div className="space-y-6">
              {/* Linked Hugging Face models */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center space-x-2">
                    <Zap className="w-4 h-4" />
                    <span>🤗 Models</span>
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
                    <span>🤗 Datasets</span>
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
                    <span>🤗 Spaces</span>
                    {paper.arxiv_id && (
                      <a
                        href={`https://huggingface.co/papers/${paper.arxiv_id.replace(/v\d+$/, "")}`}
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

      {/* Edit Tasks Dialog */}
      <EditTasksDialog
        open={isEditingTasks}
        onOpenChange={setIsEditingTasks}
        paperId={paper.id}
        arxivId={arxivId}
        initialTaskIds={paper.tasks?.map((t: Task) => parseInt(t.id)) || []}
      />

      {/* Edit Methods Dialog */}
      <EditMethodsDialog
        open={isEditingMethods}
        onOpenChange={setIsEditingMethods}
        paperId={paper.id}
        arxivId={arxivId}
        initialMethodIds={paper.methods?.map((m: { id: string }) => parseInt(m.id)) || []}
      />

      {/* Edit Repositories Dialog */}
      <EditRepositoriesDialog
        open={isEditingRepositories}
        onOpenChange={setIsEditingRepositories}
        paperId={paper.id}
        arxivId={arxivId}
        initialRepositories={
          paper.repositories?.map((r) => ({
            url: r.url,
            is_official: r.is_official || false,
          })) || []
        }
      />

      {/* Edit Evaluations Dialog */}
      <EditEvaluationsDialog
        open={isEditingEvaluations}
        onOpenChange={setIsEditingEvaluations}
        paperId={paper.id}
        arxivId={arxivId}
        initialEvaluations={evaluations || []}
      />
    </div>
  );
};

export default PaperDetail;
