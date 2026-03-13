import { QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { PropsWithChildren, ReactElement } from "react";

import { AppProviders } from "../app/providers";

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

export function renderWithProviders(ui: ReactElement) {
  const queryClient = createTestQueryClient();

  function Wrapper({ children }: PropsWithChildren) {
    return <AppProviders queryClient={queryClient}>{children}</AppProviders>;
  }

  return {
    queryClient,
    ...render(ui, { wrapper: Wrapper }),
  };
}
