import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createRouter } from "@tanstack/react-router";
import { useState } from "react";
import { routeTree } from "../routeTree.gen";

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: 1,
      },
    },
  });
}

export type RouterContext = {
  queryClient: QueryClient;
};

function createAppRouter(queryClient: QueryClient) {
  return createRouter({ routeTree, context: { queryClient } });
}

type AppRouter = ReturnType<typeof createAppRouter>;

declare module "@tanstack/react-router" {
  interface Register {
    router: AppRouter;
  }
}

export function App() {
  const [queryClient] = useState(makeQueryClient);
  const [router] = useState(() => createAppRouter(queryClient));

  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
