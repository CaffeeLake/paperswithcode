import { Card } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import Header from "@/components/Header";
import { FileText, AlertCircle, Layers } from "lucide-react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getAreas, getMethods, type Area, type Method } from "@/lib/api";
import { useMemo } from "react";
import { getMethodSlug } from "@/lib/slug";

// Method icon mapping based on method name
const getMethodIcon = (methodName: string): string => {
  const iconMap: Record<string, string> = {
    "ResNet": "🕸️",
    "Transformer": "🔄",
    "BERT": "📝",
    "Adam": "📈",
    "Dropout": "🎲",
    "Attention": "🎯",
    "Batch Normalization": "📊",
    "Convolutional Neural Network": "🧩",
    "GAN": "🎨",
    "LSTM": "🔁",
  };

  // Check for partial matches
  for (const [key, icon] of Object.entries(iconMap)) {
    if (methodName.toLowerCase().includes(key.toLowerCase())) {
      return icon;
    }
  }

  return "🔬"; // Default icon
};

interface AreaSectionProps {
  area: Area;
  methods: Method[];
}

const AreaSection = ({ area, methods }: AreaSectionProps) => {
  if (methods.length === 0) {
    return null;
  }

  return (
    <div className="mb-12">
      <h2 className="text-2xl font-semibold mb-6">{area.name}</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6 mb-6">
        {methods.map((method) => (
          <Link key={method.id} to={`/methods/${getMethodSlug(method)}`}>
            <Card className="p-6 hover:shadow-md transition-shadow cursor-pointer border bg-card h-full">
              {/* Method thumbnail image or icon */}
              {method.image_url ? (
                <div className="mb-4 rounded-lg overflow-hidden bg-muted flex items-center justify-center" style={{ height: '120px' }}>
                  <img
                    src={method.image_url}
                    alt={`${method.name} thumbnail`}
                    className="w-full h-full object-contain"
                    onError={(e) => {
                      // Fallback to icon if image fails to load
                      e.currentTarget.style.display = 'none';
                      const parent = e.currentTarget.parentElement;
                      if (parent) {
                        parent.innerHTML = `<div class="w-10 h-10 bg-muted rounded-lg flex items-center justify-center text-lg">${getMethodIcon(method.name)}</div>`;
                      }
                    }}
                  />
                </div>
              ) : (
                <div className="mb-4 flex justify-center">
                  <div className="w-10 h-10 bg-muted rounded-lg flex items-center justify-center text-lg">
                    {getMethodIcon(method.name)}
                  </div>
                </div>
              )}

              <div className="mb-3">
                <h3 className="font-semibold text-base leading-tight">{method.name}</h3>
                {method.full_name && method.full_name !== method.name && (
                  <p className="text-xs text-muted-foreground mt-1 line-clamp-1">
                    {method.full_name}
                  </p>
                )}
              </div>

              <div className="space-y-2 text-sm text-muted-foreground">
                {method.paper_count !== undefined && (
                  <div className="flex items-center space-x-1">
                    <FileText className="w-3 h-3" />
                    <span>{method.paper_count} papers</span>
                  </div>
                )}
                {method.introduced_year && (
                  <p className="text-xs">Introduced: {method.introduced_year}</p>
                )}
              </div>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
};

const Methods = () => {
  // Fetch all areas
  const { data: areasData, isLoading: isLoadingAreas, error: areasError, refetch: refetchAreas } = useQuery({
    queryKey: ['areas'],
    queryFn: () => getAreas({ page: 1, page_size: 100, ordering: 'name' }),
    staleTime: 5 * 60 * 1000,
  });

  // Fetch all methods (with proper pagination handling)
  const { data: methodsData, isLoading: isLoadingMethods, error: methodsError, refetch: refetchMethods } = useQuery({
    queryKey: ['methods'],
    queryFn: async () => {
      // Fetch first page to get total count
      const firstPage = await getMethods({ page: 1, page_size: 100, ordering: 'name' });

      // If there are more pages, fetch them all
      const totalPages = Math.ceil(firstPage.count / 100);
      if (totalPages <= 1) {
        return firstPage;
      }

      // Fetch remaining pages in parallel
      const remainingPages = await Promise.all(
        Array.from({ length: totalPages - 1 }, (_, i) =>
          getMethods({ page: i + 2, page_size: 100, ordering: 'name' })
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

  // Memoize areas and methods to prevent recalculation on every render
  const areas = useMemo(() => areasData?.results || [], [areasData?.results]);
  const allMethods = useMemo(() => methodsData?.results || [], [methodsData?.results]);

  // Group methods by area
  const methodsByArea = useMemo(() => {
    const grouped = new Map<string, Method[]>();

    // Initialize all areas
    areas.forEach(area => {
      grouped.set(area.id, []);
    });

    // Group methods by area_id
    allMethods.forEach(method => {
      if (method.area_id) {
        const existingMethods = grouped.get(method.area_id) || [];
        grouped.set(method.area_id, [...existingMethods, method]);
      }
    });

    return grouped;
  }, [areas, allMethods]);

  const isLoading = isLoadingAreas || isLoadingMethods;
  const error = areasError || methodsError;

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <main className="container mx-auto px-4 py-8">
        {/* Header Section */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold mb-4">Methods</h1>

          <div className="flex items-center space-x-4 text-muted-foreground mb-4">
            <div className="flex items-center space-x-1">
              <Layers className="w-4 h-4" />
              <span>{areasData?.count || 0} research areas</span>
            </div>
            <span>•</span>
            <div className="flex items-center space-x-1">
              <FileText className="w-4 h-4" />
              <span>{methodsData?.count || 0} AI/ML methods</span>
            </div>
          </div>

          <p className="text-muted-foreground">
            A comprehensive collection of AI/ML methods, techniques, and components
          </p>
        </div>

        {/* Error State */}
        {error && (
          <Alert variant="destructive" className="mb-6">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription className="flex items-center justify-between">
              <span>Failed to load methods. {error instanceof Error ? error.message : 'Please try again later.'}</span>
              <button
                onClick={() => {
                  refetchAreas();
                  refetchMethods();
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
          /* Methods by Area */
          areas.map((area) => {
            const methods = methodsByArea.get(area.id) || [];
            return <AreaSection key={area.id} area={area} methods={methods} />;
          })
        )}
      </main>
    </div>
  );
};

export default Methods;
