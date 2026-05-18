/**
 * Root app for the v2 frontend.
 *
 * Replaces the prototype's manual `setView(...)` state machine (App.jsx) with
 * react-router-dom routes (PLAN.md §3). Every page is bookmarkable and the
 * browser back button works as expected.
 */

import React from "react";
import {
  BrowserRouter,
  HashRouter,
  Navigate,
  Route,
  Routes,
  useParams,
} from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";

import Header from "@/components/Header";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as SonnerToaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useScrollToTop } from "@/hooks/useScrollToTop";
import { isAuthDisabled, shouldUseHashRouter } from "@/lib/apiUrl";
import { AuthProvider } from "@/lib/authContext";

// HF Static Spaces (a) boot the iframe at `/index.html` and (b) return a
// hard 404 for any deep link, so on those builds we switch to `HashRouter`.
// See `shouldUseHashRouter` in `lib/apiUrl.ts`.
const useHashRouter = shouldUseHashRouter();
const Router = useHashRouter ? HashRouter : BrowserRouter;

if (!useHashRouter && typeof window !== "undefined") {
  const hashRoute = window.location.hash;
  if (hashRoute.startsWith("#/") && !hashRoute.startsWith("#//")) {
    window.history.replaceState(null, "", hashRoute.slice(1));
  }
}

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
const SavedPapersView = React.lazy(() => import("@/views/SavedPapersView"));
const CronDashboard = React.lazy(() => import("@/pages/CronDashboard"));
const NotFound = React.lazy(() => import("@/pages/NotFound"));
const SearchOverlay = React.lazy(() => import("@/components/SearchOverlay"));

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

// On the Hugging Face Space mirror (`VITE_DISABLE_AUTH=1`) the HF OAuth
// cookie can't follow visitors across origins, so any view that requires
// sign-in (bookmarks, CRON dashboard) is a dead-end. Redirect those routes
// home so visitors don't land on empty pages.
const AuthGatedRoute: React.FC<{ element: React.ReactNode }> = ({ element }) => {
  if (isAuthDisabled()) {
    return <Navigate to="/" replace />;
  }
  return <>{element}</>;
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
            <Route path="/saved" element={<AuthGatedRoute element={<SavedPapersView />} />} />
            <Route path="/cron-dashboard" element={<AuthGatedRoute element={<CronDashboard />} />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </React.Suspense>
      </main>
      {searchOpen && (
        <React.Suspense fallback={null}>
          <SearchOverlay open={searchOpen} onClose={() => setSearchOpen(false)} />
        </React.Suspense>
      )}
    </>
  );
};

const App: React.FC = () => (
  <QueryClientProvider client={queryClient}>
    <AuthProvider>
      <TooltipProvider>
        <Router>
          <Shell />
        </Router>
        <Toaster />
        <SonnerToaster />
        {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
      </TooltipProvider>
    </AuthProvider>
  </QueryClientProvider>
);

export default App;
