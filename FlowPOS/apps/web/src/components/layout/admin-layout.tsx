"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AdminSidebar } from "./admin-sidebar";
import { useAuthStore } from "@/store/auth-store";

interface AdminLayoutProps {
  children: React.ReactNode;
}

export function AdminLayout({ children }: AdminLayoutProps) {
  const router = useRouter();
  const isPlatformAdmin = useAuthStore((s) => s.isPlatformAdmin);
  const platformAdmin = useAuthStore((s) => s.platformAdmin);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isLoading = useAuthStore((s) => s.isLoading);
  const sessionVerified = useAuthStore((s) => s.sessionVerified);

  // Guard: redirect non-admins away
  useEffect(() => {
    if (isLoading) return; // Still loading, wait
    if (!sessionVerified) return; // Haven't checked session yet

    if (!isAuthenticated) {
      router.replace("/login");
      return;
    }

    if (!isPlatformAdmin) {
      router.replace("/dashboard");
    }
  }, [isAuthenticated, isPlatformAdmin, isLoading, sessionVerified, router]);

  // Show nothing while checking auth
  if (isLoading || !sessionVerified || !isPlatformAdmin) {
    return (
      <div className="flex h-full items-center justify-center bg-[var(--background)]">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
          <span className="font-body text-sm text-[var(--muted-foreground)]">
            Loading...
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full">
      <AdminSidebar
        userName={platformAdmin?.name ?? "Admin"}
        userEmail={platformAdmin?.email ?? ""}
      />
      <main className="flex-1 overflow-y-auto bg-[var(--background)] p-6 lg:p-8">
        {children}
      </main>
    </div>
  );
}
