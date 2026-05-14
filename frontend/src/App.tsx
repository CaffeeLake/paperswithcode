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
import { AuthProvider } from "@/lib/authContext";

// Lazy-load route components so visitors only download the chunks for the
// pages they actually navigate to. Saves ~150-200 KB gzipped on first paint
// for visitors landing on a single route. See PLAN.md §4.
const FeedView = React.lazy(() => import("@/views/FeedView"));
const PapersListView = React.lazy(() => import("@/views/PapersListView"));
const PaperDetailView = React.lazy(() => import("@/views/PaperDetailView"));
const TagsIndexView = React.lazy(() => import("@/views/TagsIndexView"));
const TagBrowseView = React.lazy(() => import("@/views/TagBrowseView"));
const MethodsIndexView = React.lazy(() => import("@/views/MethodsIndexView"));
const MethodDetailView = React.lazy(() => import("@/views/MethodDetailView"));
const BenchmarkDetailView = React.lazy(() => import("@/views/BenchmarkDetailView"));
const CronDashboard = React.lazy(() => import("@/pages/CronDashboard"));
const NotFound = React.lazy(() => import("@/pages/NotFound"));

// Minimal placeholder shown while a route chunk is downloading. Each view also
// renders its own skeletons once mounted, so this fallback only flashes briefly
// (≤200 ms on a warm cache).
const RouteFallback: React.FC = () => (
  <div className="page" aria-busy="true" />
);

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
        <React.Suspense fallback={<RouteFallback />}>
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
        </React.Suspense>
      </main>
      <SearchOverlay open={searchOpen} onClose={() => setSearchOpen(false)} />
    </>
  );
};

const App: React.FC = () => (
  <QueryClientProvider client={queryClient}>
    <AuthProvider>
      <TooltipProvider>
        <BrowserRouter>
          <Shell />
        </BrowserRouter>
        <Toaster />
        <SonnerToaster />
        {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
      </TooltipProvider>
    </AuthProvider>
  </QueryClientProvider>
);

export default App;
