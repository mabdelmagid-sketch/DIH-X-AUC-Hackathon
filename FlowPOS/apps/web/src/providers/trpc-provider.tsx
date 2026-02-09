"use client";

import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { httpBatchLink } from "@trpc/client";
import superjson from "superjson";
import { trpc } from "@/lib/trpc";
import { getSupabaseClient } from "@/lib/supabase";
import { useAuthStore } from "@/store/auth-store";

function getBaseUrl() {
  if (typeof window !== "undefined") return "";
  return `http://localhost:3001`;
}

export function TRPCProvider({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 5 * 1000,
            refetchOnWindowFocus: false,
          },
        },
      })
  );

  const [trpcClient] = useState(() =>
    trpc.createClient({
      links: [
        httpBatchLink({
          url: `${getBaseUrl()}/api/trpc`,
          transformer: superjson,
          async headers() {
            const headers: Record<string, string> = {};

            const { isPinAuth, user, organization } = useAuthStore.getState();

            if (isPinAuth) {
              // PIN auth: pass user info in custom headers
              if (user) headers["x-pin-user-id"] = user.id;
              if (organization) headers["x-pin-org-id"] = organization.id;
            } else {
              // Supabase auth: pass the access token
              try {
                const supabase = getSupabaseClient();
                const { data: { session } } = await supabase.auth.getSession();
                if (session?.access_token) {
                  headers["authorization"] = `Bearer ${session.access_token}`;
                }
              } catch {
                // No session available
              }
            }

            return headers;
          },
        }),
      ],
    })
  );

  return (
    <trpc.Provider client={trpcClient} queryClient={queryClient}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </trpc.Provider>
  );
}
