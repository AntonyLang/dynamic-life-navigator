import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PropsWithChildren, useState } from "react";

function createDefaultQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: 1,
        staleTime: 5000,
        refetchOnWindowFocus: true,
      },
    },
  });
}

interface AppProvidersProps extends PropsWithChildren {
  queryClient?: QueryClient;
}

export function AppProviders({ children, queryClient: providedQueryClient }: AppProvidersProps) {
  const [queryClient] = useState(
    () => providedQueryClient ?? createDefaultQueryClient(),
  );

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

export function createAppQueryClient() {
  return createDefaultQueryClient();
}
