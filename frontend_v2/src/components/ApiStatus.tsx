import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { CheckCircle, XCircle, Loader2 } from 'lucide-react';

export function ApiStatus() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['health'],
    queryFn: () => apiClient.healthCheck(),
    refetchInterval: 30000, // Check every 30 seconds
    retry: 3,
  });

  if (isLoading) {
    return (
      <Badge variant="secondary" className="flex items-center gap-1">
        <Loader2 className="w-3 h-3 animate-spin" />
        Checking API...
      </Badge>
    );
  }

  if (error || !data) {
    return (
      <Badge variant="destructive" className="flex items-center gap-1">
        <XCircle className="w-3 h-3" />
        API Offline
      </Badge>
    );
  }

  return (
    <Badge variant="default" className="flex items-center gap-1 bg-green-500 hover:bg-green-600">
      <CheckCircle className="w-3 h-3" />
      API Connected
    </Badge>
  );
}
