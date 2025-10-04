import Header from "@/components/Header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useParams, Link } from "react-router-dom";
import { Loader2, Target } from "lucide-react";
import { useTask } from "@/hooks/useTasks";

const TaskDetail = () => {
  const { taskId } = useParams<{ taskId: string }>();
  const { data: task, isLoading, error } = useTask(taskId, !!taskId);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-4 py-8">
          <div className="flex items-center justify-center min-h-[400px]">
            <div className="flex items-center space-x-2">
              <Loader2 className="w-6 h-6 animate-spin" />
              <span>Loading task...</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error || !task) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-4 py-16 text-center">
          <h1 className="text-2xl font-bold mb-4">Task not found</h1>
          <p className="text-muted-foreground mb-4">
            {error?.message || "The requested task could not be found."}
          </p>
          <Link to="/tasks">
            <Button>Back to Tasks</Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Header />

      {/* Hero Section */}
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-start gap-8">
          {/* Task Icon */}
          <div className="w-48 h-32 bg-gradient-to-br from-blue-100 to-blue-200 rounded-lg flex items-center justify-center">
            <Target className="w-16 h-16 text-blue-600" />
          </div>

          {/* Task Info */}
          <div className="flex-1">
            <div className="flex items-center justify-between mb-4">
              <h1 className="text-4xl font-bold">{task.name}</h1>
            </div>

            <div className="flex items-center gap-6 text-lg mb-4">
              <span>
                <strong>{task.paper_count?.toLocaleString() || 0}</strong> papers
              </span>
            </div>

            {/* Breadcrumb */}
            <div className="flex items-center space-x-2 text-sm text-muted-foreground">
              <Link to="/tasks" className="hover:text-foreground transition-colors">
                Tasks
              </Link>
              <span>/</span>
              <span className="text-foreground">{task.name}</span>
            </div>
          </div>
        </div>
      </div>

      {/* About Section */}
      {task.description && (
        <div className="container mx-auto px-4 py-8">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-2xl font-bold">About</h2>
          </div>

          <Card>
            <CardContent className="p-6">
              <p className="text-muted-foreground leading-relaxed text-justify">
                {task.description}
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Papers Section */}
      <div className="container mx-auto px-4 py-8">
        <Card>
          <CardContent className="p-6">
            <div className="text-center py-8">
              <Target className="w-12 h-12 mx-auto mb-4 text-muted-foreground opacity-50" />
              <h3 className="text-lg font-semibold mb-2">Papers and Benchmarks</h3>
              <p className="text-muted-foreground">
                Papers and benchmark results for this task will be available soon.
              </p>
              {task.paper_count && task.paper_count > 0 && (
                <p className="text-sm text-muted-foreground mt-2">
                  {task.paper_count} paper{task.paper_count !== 1 ? 's' : ''} tagged with this task
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default TaskDetail;
