// Root app
import React from 'react';
import { Header } from './components.jsx';
import {
  FeedView,
  TagsIndexView,
  TagBrowseView,
  BenchmarkDetailView,
  MethodsIndexView,
  MethodDetailView,
  PaperDetailView,
  SearchOverlay,
} from './views.jsx';

const App = () => {
  const [view, setView] = React.useState('feed');
  const [activeTag, setActiveTag] = React.useState(null);
  const [activeMethod, setActiveMethod] = React.useState(null);
  const [activeBench, setActiveBench] = React.useState(null);
  const [highlightPaperId, setHighlightPaperId] = React.useState(null);
  const [activePaper, setActivePaper] = React.useState(null);
  const [sortBy, setSortBy] = React.useState('trending');
  const [period, setPeriod] = React.useState('Today');
  const [searchOpen, setSearchOpen] = React.useState(false);
  const [searchQuery, setSearchQuery] = React.useState('');
  const [upvotes, setUpvotes] = React.useState({});

  React.useEffect(() => {
    window.scrollTo(0, 0);
  }, [view, activeTag, activeMethod, activePaper]);

  React.useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const navigate = (target) => {
    setView(target);
    if (target === 'feed' || target === 'tags' || target === 'methods') {
      setActiveTag(null);
      setActiveMethod(null);
      setActivePaper(null);
    }
  };

  const openTag = (tagId, fallbackView) => {
    if (fallbackView === 'tags' || !tagId) {
      setView('tags');
      return;
    }
    setActiveTag(tagId);
    setView('tag');
  };

  const openMethod = (methodId) => {
    setActiveMethod(methodId);
    setView('method');
  };

  const openPaper = (paperId) => {
    setActivePaper(paperId);
    setView('detail');
  };

  const openBench = (tagId, slug, highlight) => {
    setActiveTag(tagId);
    setActiveBench(slug);
    setHighlightPaperId(highlight || null);
    setView('benchmark');
  };

  const upvote = (paperId) => {
    setUpvotes(prev => ({ ...prev, [paperId]: !prev[paperId] }));
  };

  const headerView =
    view === 'tag' ? 'tags' :
    view === 'method' ? 'methods' :
    view === 'detail' ? 'feed' :
    view === 'benchmark' ? 'tags' :
    view;

  return (
    <>
      <Header
        currentView={headerView}
        onNavigate={navigate}
        onOpenSearch={() => setSearchOpen(true)}
      />
      {/* {view === 'feed' && <Banner />} */}
      <main data-screen-label={
        view === 'feed' ? '01 Trending Feed' :
        view === 'tags' ? '02 Browse State-of-the-Art' :
        view === 'tag' ? `03 Domain · ${activeTag}` :
        view === 'methods' ? '04 Methods Index' :
        view === 'method' ? `05 Method · ${activeMethod}` :
        `06 Paper · ${activePaper}`
      }>
        {view === 'feed' && (
          <FeedView
            onOpenPaper={openPaper}
            onClickTag={openTag}
            sortBy={sortBy}
            setSortBy={setSortBy}
            period={period}
            setPeriod={setPeriod}
            upvotes={upvotes}
            onUpvote={upvote}
          />
        )}
        {view === 'tags' && <TagsIndexView onClickTag={openTag} />}
        {view === 'tag' && (
          <TagBrowseView
            tagId={activeTag}
            onOpenPaper={openPaper}
            onClickTag={openTag}
            onClickMethod={openMethod}
            onClickBench={openBench}
            sortBy={sortBy}
            setSortBy={setSortBy}
            upvotes={upvotes}
            onUpvote={upvote}
            onNavigate={navigate}
          />
        )}
        {view === 'benchmark' && (
          <BenchmarkDetailView
            tagId={activeTag}
            benchSlug={activeBench}
            highlightPaperId={highlightPaperId}
            onNavigate={navigate}
            onClickTag={openTag}
            onOpenPaper={openPaper}
          />
        )}
        {view === 'methods' && <MethodsIndexView onClickMethod={openMethod} />}
        {view === 'method' && (
          <MethodDetailView
            methodId={activeMethod}
            onOpenPaper={openPaper}
            onClickTag={openTag}
            onClickMethod={openMethod}
            onNavigate={navigate}
            sortBy={sortBy}
            setSortBy={setSortBy}
            upvotes={upvotes}
            onUpvote={upvote}
          />
        )}
        {view === 'detail' && (
          <PaperDetailView
            paperId={activePaper}
            onOpenPaper={openPaper}
            onClickTag={openTag}
            onClickMethod={openMethod}
            onClickBench={openBench}
            onNavigate={navigate}
            upvotes={upvotes}
            onUpvote={upvote}
          />
        )}
      </main>
      {searchOpen && (
        <SearchOverlay
          query={searchQuery}
          setQuery={setSearchQuery}
          onClose={() => setSearchOpen(false)}
          onOpenPaper={openPaper}
          onClickTag={openTag}
        />
      )}
    </>
  );
};

export default App;
