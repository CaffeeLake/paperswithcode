import { ArrowUp, MessageCircle, Calendar, ExternalLink, BookOpen, Database, Zap, Bookmark, Trophy, Edit, Loader2, Globe, X, Check, Search, Plus, Trash2, Github } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Link, useParams } from "react-router-dom";
import Header from "@/components/Header";
import { usePaperByArxivId } from "@/hooks/usePapers";
import { useHuggingFaceRepos } from "@/hooks/useHuggingFaceRepos";
import PaperResources from "@/components/PaperResources";
import { getTasks, getMethods, updatePaperTasks, updatePaperMethods, updatePaperRepositories, type Task as APITask, type Method as APIMethod } from "@/lib/api";
import { useState } from "react";
import { useQueryClient, useQuery, useMutation } from "@tanstack/react-query";
import LatexTitle from "@/components/LatexTitle";

// Type definitions
interface Task {
  id: string;
  name: string;
  slug?: string;
}

const PaperDetail = () => {
  const { arxivId } = useParams<{ arxivId: string }>();
  const { data: paper, isLoading, error } = usePaperByArxivId(arxivId || "", !!arxivId);
  const { data: hfRepos, isLoading: hfLoading } = useHuggingFaceRepos(paper?.arxiv_id);
  const queryClient = useQueryClient();

  // Admin editing state
  const [isEditingTasks, setIsEditingTasks] = useState(false);
  const [isEditingMethods, setIsEditingMethods] = useState(false);
  const [isEditingRepositories, setIsEditingRepositories] = useState(false);
  const [selectedTaskIds, setSelectedTaskIds] = useState<number[]>([]);
  const [selectedMethodIds, setSelectedMethodIds] = useState<number[]>([]);
  const [taskSearchQuery, setTaskSearchQuery] = useState("");
  const [methodSearchQuery, setMethodSearchQuery] = useState("");

  // Repository editing state (different from tasks/methods - we manage URLs directly)
  const [editedRepositories, setEditedRepositories] = useState<Array<{ url: string; is_official: boolean }>>([]);
  const [newRepositoryUrl, setNewRepositoryUrl] = useState("");

  // Fetch all tasks (using max allowed page_size of 100)
  const { data: allTasksData } = useQuery({
    queryKey: ['tasks'],
    queryFn: () => getTasks({ page_size: 100 }),
    enabled: isEditingTasks,
  });

  // Fetch all methods (using max allowed page_size of 100)
  const { data: allMethodsData } = useQuery({
    queryKey: ['methods'],
    queryFn: () => getMethods({ page_size: 100 }),
    enabled: isEditingMethods,
  });

  // Mutation for updating tasks
  const updateTasksMutation = useMutation({
    mutationFn: ({ paperId, taskIds }: { paperId: string; taskIds: number[] }) =>
      updatePaperTasks(paperId, taskIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['paper-arxiv', arxivId] });
      setIsEditingTasks(false);
    },
  });

  // Mutation for updating methods
  const updateMethodsMutation = useMutation({
    mutationFn: ({ paperId, methodIds }: { paperId: string; methodIds: number[] }) =>
      updatePaperMethods(paperId, methodIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['paper-arxiv', arxivId] });
      setIsEditingMethods(false);
    },
  });

  // Mutation for updating repositories (now sends URLs instead of IDs)
  const updateRepositoriesMutation = useMutation({
    mutationFn: ({ paperId, repositories }: { paperId: string; repositories: Array<{ url: string; is_official: boolean }> }) =>
      updatePaperRepositories(paperId, repositories),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['paper-arxiv', arxivId] });
      setIsEditingRepositories(false);
      setNewRepositoryUrl("");
    },
  });

  // Generate colors for authors (similar to the original hardcoded approach)
  const getAuthorColor = (index: number) => {
    const colors = ["#3B82F6", "#8B5CF6", "#EF4444", "#10B981", "#F59E0B", "#EC4899", "#06B6D4", "#84CC16", "#F97316"];
    return colors[index % colors.length];
  };

  // Initialize selected items when opening dialog
  const handleEditTasks = () => {
    if (paper?.tasks) {
      setSelectedTaskIds(paper.tasks.map((t: Task) => parseInt(t.id)));
    }
    setTaskSearchQuery("");
    setIsEditingTasks(true);
  };

  const handleEditMethods = () => {
    if (paper?.methods) {
      setSelectedMethodIds(paper.methods.map((m: { id: string }) => parseInt(m.id)));
    }
    setMethodSearchQuery("");
    setIsEditingMethods(true);
  };

  const handleEditRepositories = () => {
    if (paper?.repositories) {
      // Initialize with current repositories
      setEditedRepositories(
        paper.repositories.map((r) => ({
          url: r.url,
          is_official: r.is_official || false,
        }))
      );
    } else {
      setEditedRepositories([]);
    }
    setNewRepositoryUrl("");
    setIsEditingRepositories(true);
  };

  // Save handlers
  const handleSaveTasks = () => {
    if (paper?.id) {
      updateTasksMutation.mutate({ paperId: paper.id, taskIds: selectedTaskIds });
    }
  };

  const handleSaveMethods = () => {
    if (paper?.id) {
      updateMethodsMutation.mutate({ paperId: paper.id, methodIds: selectedMethodIds });
    }
  };

  const handleSaveRepositories = () => {
    if (paper?.id) {
      updateRepositoriesMutation.mutate({ paperId: paper.id, repositories: editedRepositories });
    }
  };

  const handleAddRepository = () => {
    const trimmedUrl = newRepositoryUrl.trim();
    if (!trimmedUrl) return;

    // Check if URL already exists
    if (editedRepositories.some(r => r.url === trimmedUrl)) {
      alert("This repository URL is already added");
      return;
    }

    setEditedRepositories([...editedRepositories, { url: trimmedUrl, is_official: false }]);
    setNewRepositoryUrl("");
  };

  const handleRemoveRepository = (url: string) => {
    setEditedRepositories(editedRepositories.filter(r => r.url !== url));
  };

  const handleToggleOfficial = (url: string) => {
    setEditedRepositories(
      editedRepositories.map(r =>
        r.url === url ? { ...r, is_official: !r.is_official } : r
      )
    );
  };

  // Filter tasks based on search query
  const filteredTasks = allTasksData?.results?.filter((task: APITask) => {
    const searchLower = taskSearchQuery.toLowerCase();
    return (
      task.name.toLowerCase().includes(searchLower) ||
      (task.description && task.description.toLowerCase().includes(searchLower))
    );
  });

  // Filter methods based on search query
  const filteredMethods = allMethodsData?.results?.filter((method: APIMethod) => {
    const searchLower = methodSearchQuery.toLowerCase();
    return (
      method.name.toLowerCase().includes(searchLower) ||
      (method.full_name && method.full_name.toLowerCase().includes(searchLower)) ||
      (method.description && method.description.toLowerCase().includes(searchLower))
    );
  });

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
                  <p className="leading-relaxed text-justify text-foreground">{paper.abstract}</p>
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
              onEditTasks={handleEditTasks}
              onEditMethods={handleEditMethods}
              onEditRepositories={handleEditRepositories}
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

      {/* Edit Tasks Dialog */}
      <Dialog open={isEditingTasks} onOpenChange={setIsEditingTasks}>
        <DialogContent className="max-w-2xl max-h-[600px]">
          <DialogHeader>
            <DialogTitle>Edit Paper Tasks</DialogTitle>
            <DialogDescription>
              Select the tasks that this paper addresses. You can select multiple tasks.
            </DialogDescription>
          </DialogHeader>
          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              type="text"
              placeholder="Search tasks..."
              value={taskSearchQuery}
              onChange={(e) => setTaskSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
          <div className="py-4 overflow-y-auto max-h-[400px]">
            {filteredTasks && filteredTasks.length > 0 ? (
              <div className="space-y-2">
                {filteredTasks.map((task: APITask) => (
                  <div key={task.id} className="flex items-center space-x-2 p-2 hover:bg-muted/50 rounded-md">
                    <Checkbox
                      id={`task-${task.id}`}
                      checked={selectedTaskIds.includes(parseInt(task.id))}
                      onCheckedChange={(checked) => {
                        const taskId = parseInt(task.id);
                        if (checked) {
                          setSelectedTaskIds([...selectedTaskIds, taskId]);
                        } else {
                          setSelectedTaskIds(selectedTaskIds.filter(id => id !== taskId));
                        }
                      }}
                    />
                    <label
                      htmlFor={`task-${task.id}`}
                      className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer flex-1"
                    >
                      {task.name}
                      {task.description && (
                        <span className="block text-xs text-muted-foreground font-normal mt-1">
                          {task.description.substring(0, 100)}{task.description.length > 100 ? '...' : ''}
                        </span>
                      )}
                    </label>
                  </div>
                ))}
              </div>
            ) : allTasksData?.results ? (
              <div className="text-center py-8 text-muted-foreground">
                <Search className="w-8 h-8 mx-auto mb-2 opacity-50" />
                <p>No tasks found matching "{taskSearchQuery}"</p>
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <Loader2 className="w-8 h-8 mx-auto mb-2 animate-spin" />
                <p>Loading tasks...</p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsEditingTasks(false)}>
              Cancel
            </Button>
            <Button onClick={handleSaveTasks} disabled={updateTasksMutation.isPending}>
              {updateTasksMutation.isPending ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <Check className="w-4 h-4 mr-2" />
                  Save Changes
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Methods Dialog */}
      <Dialog open={isEditingMethods} onOpenChange={setIsEditingMethods}>
        <DialogContent className="max-w-2xl max-h-[600px]">
          <DialogHeader>
            <DialogTitle>Edit Paper Methods</DialogTitle>
            <DialogDescription>
              Select the methods and techniques used in this paper. You can select multiple methods.
            </DialogDescription>
          </DialogHeader>
          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              type="text"
              placeholder="Search methods..."
              value={methodSearchQuery}
              onChange={(e) => setMethodSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
          <div className="py-4 overflow-y-auto max-h-[400px]">
            {filteredMethods && filteredMethods.length > 0 ? (
              <div className="space-y-2">
                {filteredMethods.map((method: APIMethod) => (
                  <div key={method.id} className="flex items-center space-x-2 p-2 hover:bg-muted/50 rounded-md">
                    <Checkbox
                      id={`method-${method.id}`}
                      checked={selectedMethodIds.includes(parseInt(method.id))}
                      onCheckedChange={(checked) => {
                        const methodId = parseInt(method.id);
                        if (checked) {
                          setSelectedMethodIds([...selectedMethodIds, methodId]);
                        } else {
                          setSelectedMethodIds(selectedMethodIds.filter(id => id !== methodId));
                        }
                      }}
                    />
                    <label
                      htmlFor={`method-${method.id}`}
                      className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer flex-1"
                    >
                      {method.name}
                      {method.full_name && method.full_name !== method.name && (
                        <span className="block text-xs text-muted-foreground font-normal">
                          {method.full_name}
                        </span>
                      )}
                      {method.description && (
                        <span className="block text-xs text-muted-foreground font-normal mt-1">
                          {method.description.substring(0, 100)}{method.description.length > 100 ? '...' : ''}
                        </span>
                      )}
                    </label>
                  </div>
                ))}
              </div>
            ) : allMethodsData?.results ? (
              <div className="text-center py-8 text-muted-foreground">
                <Search className="w-8 h-8 mx-auto mb-2 opacity-50" />
                <p>No methods found matching "{methodSearchQuery}"</p>
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <Loader2 className="w-8 h-8 mx-auto mb-2 animate-spin" />
                <p>Loading methods...</p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsEditingMethods(false)}>
              Cancel
            </Button>
            <Button onClick={handleSaveMethods} disabled={updateMethodsMutation.isPending}>
              {updateMethodsMutation.isPending ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <Check className="w-4 h-4 mr-2" />
                  Save Changes
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Repositories Dialog */}
      <Dialog open={isEditingRepositories} onOpenChange={setIsEditingRepositories}>
        <DialogContent className="max-w-2xl max-h-[600px]">
          <DialogHeader>
            <DialogTitle>Edit Paper Repositories</DialogTitle>
            <DialogDescription>
              Add or remove GitHub repository URLs associated with this paper. Mark repositories as official if they are created by the paper authors.
            </DialogDescription>
          </DialogHeader>

          {/* Add new repository */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Add Repository URL</label>
            <div className="flex space-x-2">
              <Input
                type="url"
                placeholder="https://github.com/owner/repo"
                value={newRepositoryUrl}
                onChange={(e) => setNewRepositoryUrl(e.target.value)}
                onKeyPress={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    handleAddRepository();
                  }
                }}
                className="flex-1"
              />
              <Button onClick={handleAddRepository} size="sm" disabled={!newRepositoryUrl.trim()}>
                <Plus className="w-4 h-4 mr-1" />
                Add
              </Button>
            </div>
          </div>

          {/* List of repositories */}
          <div className="py-4 overflow-y-auto max-h-[350px]">
            {editedRepositories.length > 0 ? (
              <div className="space-y-2">
                {editedRepositories.map((repo, index) => (
                  <div key={index} className="flex items-center space-x-2 p-3 bg-muted/30 rounded-lg hover:bg-muted/50 transition-colors">
                    <Github className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center space-x-2">
                        <span className="text-sm font-medium text-paper-blue truncate">
                          {repo.url}
                        </span>
                        {repo.is_official && (
                          <Badge variant="secondary" className="text-xs">Official</Badge>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center space-x-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleToggleOfficial(repo.url)}
                        className="h-8 px-2"
                        title={repo.is_official ? "Mark as unofficial" : "Mark as official"}
                      >
                        <Check className={`w-4 h-4 ${repo.is_official ? 'text-green-600' : 'text-muted-foreground'}`} />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRemoveRepository(repo.url)}
                        className="h-8 px-2 text-destructive hover:text-destructive"
                        title="Remove repository"
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <Github className="w-8 h-8 mx-auto mb-2 opacity-50" />
                <p className="text-sm">No repositories added yet</p>
                <p className="text-xs mt-1">Add a repository URL above to get started</p>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setIsEditingRepositories(false)}>
              Cancel
            </Button>
            <Button onClick={handleSaveRepositories} disabled={updateRepositoriesMutation.isPending}>
              {updateRepositoriesMutation.isPending ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <Check className="w-4 h-4 mr-2" />
                  Save Changes
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default PaperDetail;
