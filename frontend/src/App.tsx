/**
 * Root app for the v2 frontend.
 *
 * Replaces the prototype's manual `setView(...)` state machine (App.jsx) with
 * react-router-dom routes (PLAN.md §3). Every page is bookmarkable and the
 * browser back button works as expected.
 */

import React from "react";
import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";

import { Header } from "@/components";
import SearchOverlay from "@/components/SearchOverlay";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as SonnerToaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useScrollToTop } from "@/hooks/useScrollToTop";

import FeedView from "@/views/FeedView";
import PapersListView from "@/views/PapersListView";
import PaperDetailView from "@/views/PaperDetailView";
import TagsIndexView from "@/views/TagsIndexView";
import TagBrowseView from "@/views/TagBrowseView";
import MethodsIndexView from "@/views/MethodsIndexView";
import MethodDetailView from "@/views/MethodDetailView";
import BenchmarkDetailView from "@/views/BenchmarkDetailView";
import CronDashboard from "@/pages/CronDashboard";
import NotFound from "@/pages/NotFound";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

const LegacyPaperRedirect: React.FC = () => {
  const { arxivId } = useParams();
  return <Navigate to={arxivId ? `/paper/${arxivId}` : "/papers"} replace />;
};

const Shell: React.FC = () => {
  const [searchOpen, setSearchOpen] = React.useState(false);

  useScrollToTop();

  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return (
    <>
      <Header onOpenSearch={() => setSearchOpen(true)} />
      <main>
        <Routes>
          <Route path="/" element={<FeedView />} />
          <Route path="/papers" element={<PapersListView />} />
          <Route path="/papers/:arxivId" element={<LegacyPaperRedirect />} />
          <Route path="/paper/:arxivId" element={<PaperDetailView />} />
          <Route path="/tasks" element={<TagsIndexView />} />
          <Route path="/tasks/:taskSlug" element={<TagBrowseView />} />
          <Route path="/methods" element={<MethodsIndexView />} />
          <Route path="/methods/:methodSlug" element={<MethodDetailView />} />
          <Route path="/benchmark/:datasetSlug" element={<BenchmarkDetailView />} />
          <Route path="/cron-dashboard" element={<CronDashboard />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
      <SearchOverlay open={searchOpen} onClose={() => setSearchOpen(false)} />
    </>
  );
};

const App: React.FC = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <BrowserRouter>
        <Shell />
      </BrowserRouter>
      <Toaster />
      <SonnerToaster />
      {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
