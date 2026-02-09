"use client";

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import { useAuthStore } from "@/store/auth-store";

/**
 * Initializes auth session on app load.
 * Calls syncWithSupabase once to check if user has an active Supabase session.
 * Skips on auth pages (login, pin) to prevent stale session interference.
 * Renders nothing - purely side-effect component.
 */
export function SessionInitializer() {
  const { syncWithSupabase, sessionVerified, isPinAuth } = useAuthStore();
  const initialized = useRef(false);
  const pathname = usePathname();

  useEffect(() => {
    // Skip session init on auth pages — login page handles its own auth flow
    const isAuthPage = pathname === "/login" || pathname === "/pin";
    if (isAuthPage) return;

    // Only sync once on mount, and skip if already verified or using PIN auth
    if (!initialized.current && !sessionVerified && !isPinAuth) {
      initialized.current = true;
      syncWithSupabase();
    }
  }, [syncWithSupabase, sessionVerified, isPinAuth, pathname]);

  return null;
}
