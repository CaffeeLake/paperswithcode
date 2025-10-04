import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate, useParams } from "react-router-dom";
import Index from "./pages/Index";
import Papers from "./pages/Papers";
import PaperDetail from "./pages/PaperDetail";
import Tasks from "./pages/Tasks";
import TaskDetail from "./pages/TaskDetail";
import Methods from "./pages/Methods";
import MethodDetail from "./pages/MethodDetail";
import Benchmark from "./pages/Benchmark";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 3,
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
      staleTime: 5 * 60 * 1000, // 5 minutes
      refetchOnWindowFocus: false,
      refetchOnMount: true,
    },
  },
});

// Redirect component for /papers/:arxivId to /paper/:arxivId
const PapersRedirect = () => {
  const { arxivId } = useParams<{ arxivId: string }>();
  return <Navigate to={`/paper/${arxivId}`} replace />;
};

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Index />} />
          <Route path="/papers" element={<Papers />} />
          <Route path="/papers/:arxivId" element={<PapersRedirect />} />
          <Route path="/paper/:arxivId" element={<PaperDetail />} />
          <Route path="/tasks" element={<Tasks />} />
          <Route path="/tasks/:taskId" element={<TaskDetail />} />
          <Route path="/methods" element={<Methods />} />
          <Route path="/methods/:methodId" element={<MethodDetail />} />
          <Route path="/benchmark/:benchmark" element={<Benchmark />} />
          {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
