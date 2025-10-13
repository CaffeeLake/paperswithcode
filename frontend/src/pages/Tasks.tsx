import { Card } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import Header from "@/components/Header";
import { Layers, FileText, AlertCircle } from "lucide-react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getAreas, getAreaTasks, getTasks, type Area, type Task } from "@/lib/api";

// Task icon mapping based on task name
const getTaskIcon = (taskName: string): string => {
  const iconMap: Record<string, string> = {
    "Image Classification": "🖼️",
    "Object Detection": "🔍",
    "OCR": "📄",
    "Semantic Segmentation": "🎯",
    "Image Generation": "🎨",
    "Denoising": "✨",
    "Machine Translation": "🔄",
    "Language Modeling": "📝",
    "Language Modelling": "📝",
    "Question Answering": "❓",
    "Sentiment Analysis": "😊",
    "Text Generation": "📄",
    "Vision Language Action Models": "🤖",
    "Vision Language Models": "👁️",
    "Vision-Language Models": "👁️",
    "Computer Use Agents": "💻",
    "Automatic Speech Recognition": "🎤",
  };

  return iconMap[taskName] || "📊";
};

interface AreaWithTasks extends Area {
  tasks: Task[];
}

const AreaSection = ({ area }: { area: Area }) => {
  // Fetch tasks for this area
  const { data: tasksData, isLoading: isLoadingTasks } = useQuery({
    queryKey: ['area-tasks', area.id],
    queryFn: () => getAreaTasks(area.id, { page: 1, page_size: 100 }),
    staleTime: 5 * 60 * 1000, // Cache for 5 minutes
  });

  const tasks = tasksData?.results || [];

  return (
    <div className="mb-12">
      <h2 className="text-2xl font-semibold mb-6">{area.name}</h2>

      {isLoadingTasks ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6 mb-6">
          {[...Array(5)].map((_, i) => (
            <Card key={i} className="p-6">
              <div className="flex items-start space-x-3 mb-4">
                <Skeleton className="w-10 h-10 rounded-lg" />
                <Skeleton className="h-6 flex-1" />
              </div>
              <div className="space-y-2">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-4 w-24" />
              </div>
            </Card>
          ))}
        </div>
      ) : tasks.length > 0 ? (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6 mb-6">
            {tasks.map((task) => (
              <Link key={task.id} to={`/tasks/${task.slug || task.id}`}>
                <Card className="p-6 hover:shadow-md transition-shadow cursor-pointer border bg-card h-full">
                  <div className="flex items-start space-x-3 mb-4">
                    <div className="w-10 h-10 bg-muted rounded-lg flex items-center justify-center text-lg">
                      {getTaskIcon(task.name)}
                    </div>
                    <div className="flex-1">
                      <h3 className="font-semibold text-base leading-tight">{task.name}</h3>
                    </div>
                  </div>

                  <div className="space-y-2 text-sm text-muted-foreground">
                    {task.paper_count !== undefined && (
                      <div className="flex items-center space-x-1">
                        <FileText className="w-3 h-3" />
                        <span>{task.paper_count} papers</span>
                      </div>
                    )}
                    {task.description && (
                      <p className="text-xs line-clamp-2">{task.description}</p>
                    )}
                  </div>
                </Card>
              </Link>
            ))}
          </div>

          {tasksData && tasksData.count > tasks.length && (
            <div className="text-primary font-medium">
              ▶ See all {tasksData.count} tasks
            </div>
          )}
        </>
      ) : (
        <p className="text-muted-foreground">No tasks available for this area yet.</p>
      )}
    </div>
  );
};

const Tasks = () => {
  // Fetch all areas
  const { data: areasData, isLoading: isLoadingAreas, error: areasError, refetch: refetchAreas } = useQuery({
    queryKey: ['areas'],
    queryFn: async () => {
      console.log('[Tasks] Starting to fetch areas...');
      try {
        const result = await getAreas({ page: 1, page_size: 100, ordering: 'name' });
        console.log('[Tasks] Successfully fetched areas:', result);
        return result;
      } catch (err) {
        console.error('[Tasks] Failed to fetch areas:', err);
        throw err;
      }
    },
    staleTime: 5 * 60 * 1000, // Cache for 5 minutes
    retry: 3,
  });

  // Fetch all tasks to get total count
  const { data: tasksData, isLoading: isLoadingTasks, error: tasksError, refetch: refetchTasks } = useQuery({
    queryKey: ['all-tasks'],
    queryFn: async () => {
      // Fetch first page to get total count
      const firstPage = await getTasks({ page: 1, page_size: 100, ordering: 'name' });

      // If there are more pages, fetch them all
      const totalPages = Math.ceil(firstPage.count / 100);
      if (totalPages <= 1) {
        return firstPage;
      }

      // Fetch remaining pages in parallel
      const remainingPages = await Promise.all(
        Array.from({ length: totalPages - 1 }, (_, i) =>
          getTasks({ page: i + 2, page_size: 100, ordering: 'name' })
        )
      );

      // Combine all results
      return {
        count: firstPage.count,
        next_page: null,
        previous_page: null,
        results: [
          ...firstPage.results,
          ...remainingPages.flatMap(page => page.results)
        ]
      };
    },
    staleTime: 5 * 60 * 1000,
  });

  const areas = areasData?.results || [];
  const isLoading = isLoadingAreas || isLoadingTasks;
  const error = areasError || tasksError;

  console.log('[Tasks] Render state:', {
    isLoading,
    error: error?.message,
    areasCount: areas.length,
    tasksCount: tasksData?.count,
    areasData
  });

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <main className="container mx-auto px-4 py-8">
        {/* Header Section */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold mb-4">Browse State-of-the-Art</h1>

          <div className="flex items-center space-x-4 text-muted-foreground mb-4">
            <div className="flex items-center space-x-1">
              <Layers className="w-4 h-4" />
              <span>{areasData?.count || 0} research areas</span>
            </div>
            <span>•</span>
            <div className="flex items-center space-x-1">
              <FileText className="w-4 h-4" />
              <span>{tasksData?.count || 0} AI/ML tasks</span>
            </div>
          </div>

          <p className="text-muted-foreground">
            A comprehensive collection of AI/ML tasks organized by research area
          </p>
        </div>

        {/* Error State */}
        {error && (
          <Alert variant="destructive" className="mb-6">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription className="flex items-center justify-between">
              <span>Failed to load tasks. {error instanceof Error ? error.message : 'Please try again later.'}</span>
              <button
                onClick={() => {
                  refetchAreas();
                  refetchTasks();
                }}
                className="ml-4 px-3 py-1 bg-white text-red-600 rounded hover:bg-gray-100 text-sm font-medium"
              >
                Retry
              </button>
            </AlertDescription>
          </Alert>
        )}

        {/* Loading State */}
        {isLoading ? (
          <div className="space-y-12">
            {[...Array(3)].map((_, i) => (
              <div key={i}>
                <Skeleton className="h-8 w-64 mb-6" />
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6">
                  {[...Array(5)].map((_, j) => (
                    <Card key={j} className="p-6">
                      <div className="flex items-start space-x-3 mb-4">
                        <Skeleton className="w-10 h-10 rounded-lg" />
                        <Skeleton className="h-6 flex-1" />
                      </div>
                      <div className="space-y-2">
                        <Skeleton className="h-4 w-32" />
                        <Skeleton className="h-4 w-24" />
                      </div>
                    </Card>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          /* Task Categories by Area */
          areas.map((area) => <AreaSection key={area.id} area={area} />)
        )}
      </main>
    </div>
  );
};

export default Tasks;
