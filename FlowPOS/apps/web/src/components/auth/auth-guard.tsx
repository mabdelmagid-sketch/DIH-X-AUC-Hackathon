"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/auth-store";

interface AuthGuardProps {
  children: React.ReactNode;
  /** Where to redirect if not authenticated */
  redirectTo?: string;
  /** If true, also calls syncWithSupabase on mount to verify session */
  verifySession?: boolean;
}

export function AuthGuard({ children, redirectTo = "/login", verifySession = true }: AuthGuardProps) {
  const router = useRouter();
  const { isAuthenticated, isLoading, sessionVerified, syncWithSupabase } = useAuthStore();

  // Verify session with Supabase on mount
  useEffect(() => {
    if (verifySession && !sessionVerified) {
      syncWithSupabase();
    }
  }, [verifySession, sessionVerified, syncWithSupabase]);

  // Redirect to login if not authenticated (after session check completes)
  useEffect(() => {
    if (sessionVerified && !isAuthenticated && !isLoading) {
      router.replace(redirectTo);
    }
  }, [sessionVerified, isAuthenticated, isLoading, router, redirectTo]);

  // Show loading state while checking auth
  if (isLoading || !sessionVerified) {
    return (
      <div className="flex h-full items-center justify-center bg-[var(--background)]">
        <div className="flex flex-col items-center gap-4">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
          <p className="text-sm font-body text-[var(--muted-foreground)]">Loading...</p>
        </div>
      </div>
    );
  }

  // Don't render children if not authenticated
  if (!isAuthenticated) {
    return null;
  }

  return <>{children}</>;
}
