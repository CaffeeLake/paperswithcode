import { useQuery } from '@tanstack/react-query';

interface HuggingFaceRepoCounts {
  models: number;
  datasets: number;
  spaces: number;
  isLimited: boolean; // Indicates if counts might be higher than displayed
}

// Maximum pages to fetch for accurate counting (prevents excessive API calls)
const MAX_PAGES_TO_FETCH = 5; // This gives us up to 500 items per category
const ITEMS_PER_PAGE = 100;

const fetchCountForType = async (type: 'models' | 'datasets' | 'spaces', arxivId: string): Promise<{ count: number; isLimited: boolean }> => {
  try {
    // Get count from the repos endpoint
    const reposResponse = await fetch(`https://huggingface.co/api/arxiv/${arxivId}/repos`);

    if (!reposResponse.ok) {
      console.warn(`Failed to fetch repos for arXiv:${arxivId}, status: ${reposResponse.status}`);
      return { count: 0, isLimited: false };
    }

    const reposData = await reposResponse.json();
    const count = (reposData[type] || []).length;

    console.log(`${type} count for arXiv:${arxivId}: ${count}`);

    // If we got less than 100, that's the accurate count
    if (count < 100) {
      return { count, isLimited: false };
    }

    // If we got exactly 100, it's likely capped - mark as limited
    return { count, isLimited: true };

  } catch (error) {
    console.warn(`Failed to fetch ${type} count for arXiv:${arxivId}:`, error);
    return { count: 0, isLimited: false };
  }
};

const fetchHuggingFaceRepos = async (arxivId: string): Promise<HuggingFaceRepoCounts> => {
  // Fetch counts for all three types in parallel
  const [modelsResult, datasetsResult, spacesResult] = await Promise.all([
    fetchCountForType('models', arxivId),
    fetchCountForType('datasets', arxivId),
    fetchCountForType('spaces', arxivId)
  ]);

  return {
    models: modelsResult.count,
    datasets: datasetsResult.count,
    spaces: spacesResult.count,
    isLimited: modelsResult.isLimited || datasetsResult.isLimited || spacesResult.isLimited
  };
};

export const useHuggingFaceRepos = (arxivId: string | null | undefined) => {
  return useQuery({
    queryKey: ['huggingface-repos', arxivId],
    queryFn: () => fetchHuggingFaceRepos(arxivId!),
    enabled: !!arxivId,
    staleTime: 10 * 60 * 1000, // 10 minutes (longer cache due to more expensive operation)
    retry: 1,
  });
};
