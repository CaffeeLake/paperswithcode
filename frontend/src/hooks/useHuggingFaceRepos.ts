import { useQuery } from '@tanstack/react-query';

interface HuggingFaceRepoCounts {
  models: number;
  datasets: number;
  spaces: number;
  isLimited: boolean; // Indicates if counts might be higher than displayed
  paperExists: boolean; // Whether huggingface.co/papers/<id> exists
}

const canonicalArxivId = (arxivId: string) => arxivId.replace(/v\d+$/, "");

const countFromRepos = (
  reposData: Record<string, unknown[]>,
  type: 'models' | 'datasets' | 'spaces',
): { count: number; isLimited: boolean } => {
  const count = (reposData[type] || []).length;
  if (count < 100) return { count, isLimited: false };
  return { count, isLimited: true };
};

const checkPaperExists = async (arxivId: string): Promise<boolean> => {
  try {
    const response = await fetch(`https://huggingface.co/api/papers/${canonicalArxivId(arxivId)}`);
    return response.ok;
  } catch {
    return false;
  }
};

const fetchHuggingFaceRepos = async (arxivId: string): Promise<HuggingFaceRepoCounts> => {
  const id = canonicalArxivId(arxivId);

  const [reposData, paperExists] = await Promise.all([
    fetch(`https://huggingface.co/api/arxiv/${id}/repos`)
      .then(async (response) => {
        if (!response.ok) {
          console.warn(`Failed to fetch repos for arXiv:${id}, status: ${response.status}`);
          return null;
        }
        return response.json() as Promise<Record<string, unknown[]>>;
      })
      .catch((error) => {
        console.warn(`Failed to fetch repos for arXiv:${id}:`, error);
        return null;
      }),
    checkPaperExists(id),
  ]);

  if (!reposData) {
    return { models: 0, datasets: 0, spaces: 0, isLimited: false, paperExists };
  }

  const modelsResult = countFromRepos(reposData, 'models');
  const datasetsResult = countFromRepos(reposData, 'datasets');
  const spacesResult = countFromRepos(reposData, 'spaces');

  return {
    models: modelsResult.count,
    datasets: datasetsResult.count,
    spaces: spacesResult.count,
    isLimited: modelsResult.isLimited || datasetsResult.isLimited || spacesResult.isLimited,
    paperExists,
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
