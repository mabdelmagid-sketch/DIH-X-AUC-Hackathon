import { create } from "zustand";
import { persist } from "zustand/middleware";
import { type UserRole, type Permission, hasPermission } from "@/lib/permissions";
import { type PartnerUserRole, type PartnerPermission, hasPartnerPermission } from "@/lib/partner-permissions";
import { getSupabaseClient } from "@/lib/supabase";

export interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  avatar?: string;
  organizationId: string;
  locationId: string;
  employeeId?: string;
  pin?: string;
}

export interface OrganizationSettings {
  currency: string;
  timezone: string;
  taxRate: number; // In basis points (825 = 8.25%)
  taxInclusive: boolean;
  receiptHeader?: string;
  receiptFooter?: string;
  showLogo: boolean;
  requirePin: boolean;
  allowNegative: boolean;
  defaultTipPercentages: number[];
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  logo?: string;
  // Settings from organization_settings table
  taxRate: number;
  taxInclusive: boolean;
  currency: string;
  timezone: string;
  settings?: OrganizationSettings;
}

export interface Location {
  id: string;
  name: string;
  address?: string;
}

export interface PlatformAdmin {
  id: string;
  email: string;
  name: string;
}

export interface PartnerUser {
  id: string;
  email: string;
  name: string;
  role: PartnerUserRole;
  partnerId: string;
}

export interface Partner {
  id: string;
  name: string;
  slug: string;
  logo?: string;
  defaultPosName?: string;
  primaryColor?: string;
  secondaryColor?: string;
}

export interface StoreConfig {
  id: string;
  name: string;
  code: string; // Organization slug
  logo?: string;
}

export interface ImpersonationSession {
  id: string;
  userId: string;
  userName: string;
  organizationId: string;
  organizationName: string;
  reason: string;
  startedAt: string;
}

interface AuthState {
  user: User | null;
  organization: Organization | null;
  location: Location | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  useSupabase: boolean; // Toggle for Supabase vs demo mode
  sessionVerified: boolean; // True only after Supabase session is verified (not persisted)
  // Platform admin state
  isPlatformAdmin: boolean;
  platformAdmin: PlatformAdmin | null;
  impersonation: ImpersonationSession | null;
  // Partner/reseller state
  isPartnerUser: boolean;
  partnerUser: PartnerUser | null;
  partner: Partner | null;
  // Store configuration (persists even when logged out)
  storeConfig: StoreConfig | null;
  isPinAuth: boolean; // True if authenticated via PIN
}

interface AuthActions {
  loginWithSupabase: (email: string, password: string) => Promise<{ error: Error | null }>;
  signUpWithSupabase: (email: string, password: string, name: string, orgName: string) => Promise<{ error: Error | null }>;
  logout: () => Promise<void>;
  logoutUser: () => void; // Logout user but keep store config
  switchLocation: (location: Location) => void;
  updateUser: (updates: Partial<User>) => void;
  hasPermission: (permission: Permission) => boolean;
  hasAnyPermission: (permissions: Permission[]) => boolean;
  // Partner permission helpers
  checkPartnerPermission: (permission: PartnerPermission) => boolean;
  hasAnyPartnerPermission: (permissions: PartnerPermission[]) => boolean;
  setLoading: (loading: boolean) => void;
  syncWithSupabase: () => Promise<void>;
  // Store configuration
  setStoreConfig: (config: StoreConfig | null) => void;
  clearStoreConfig: () => void;
  // PIN-based login
  loginWithPin: (storeCode: string, pin: string, pinVerifyResult: PinVerifyResult) => void;
}

// Type for PIN verification result from API
export interface PinVerifyResult {
  employee: {
    id: string;
    user_id: string;
    location_id: string;
    pin: string | null;
    hourly_rate: number | null;
    is_active: boolean;
  };
  user: {
    id: string;
    email: string;
    name: string;
    role: string;
    organization_id: string;
  };
  organization: {
    id: string;
    name: string;
    slug: string;
    logo: string | null;
  };
  organizationSettings: {
    currency: string;
    timezone: string;
    tax_rate: number;
    tax_inclusive: boolean;
    receipt_header: string | null;
    receipt_footer: string | null;
    show_logo: boolean;
    require_pin: boolean;
    allow_negative: boolean;
    default_tip_percentages: number[];
  } | null;
  location: {
    id: string;
    name: string;
    address: string | null;
  } | null;
}

export const useAuthStore = create<AuthState & AuthActions>()(
  persist(
    (set, get) => ({
      // State
      user: null,
      organization: null,
      location: null,
      isAuthenticated: false,
      isLoading: true,
      useSupabase: true, // Default to Supabase mode
      sessionVerified: false, // Only true after Supabase session is verified
      // Platform admin state
      isPlatformAdmin: false,
      platformAdmin: null,
      impersonation: null,
      // Partner/reseller state
      isPartnerUser: false,
      partnerUser: null,
      partner: null,
      // Store configuration
      storeConfig: null,
      isPinAuth: false,

      // Actions
      loginWithSupabase: async (email: string, password: string) => {
        console.log("[Auth] loginWithSupabase: START");
        // Clear ALL stale state before login attempt
        set({
          isLoading: true,
          user: null,
          organization: null,
          location: null,
          isPlatformAdmin: false,
          platformAdmin: null,
          isPartnerUser: false,
          partnerUser: null,
          partner: null,
          impersonation: null,
          isAuthenticated: false,
          sessionVerified: false,
        });

        let supabase;
        try {
          supabase = getSupabaseClient();
          console.log("[Auth] loginWithSupabase: Got Supabase client");
        } catch (clientError) {
          console.error("[Auth] loginWithSupabase: Failed to get Supabase client:", clientError);
          set({ isLoading: false, sessionVerified: true });
          return { error: new Error("Failed to initialize authentication") };
        }

        // Helper to add timeout to promises
        const withTimeout = <T>(promise: Promise<T>, ms: number, name: string): Promise<T> => {
          return Promise.race([
            promise,
            new Promise<T>((_, reject) =>
              setTimeout(() => {
                console.log(`[Auth] ${name} timeout triggered after ${ms}ms`);
                reject(new Error(`${name} timed out. Please try again.`));
              }, ms)
            )
          ]);
        };

        try {
          console.log("[Auth] loginWithSupabase: Calling signInWithPassword...");
          const { error: authError, data } = await withTimeout(
            supabase.auth.signInWithPassword({
              email,
              password,
            }),
            30000,
            "Login"
          );
          console.log("[Auth] loginWithSupabase: signInWithPassword returned", {
            hasError: !!authError,
            errorMessage: authError?.message,
            hasSession: !!data?.session
          });

          if (authError) {
            set({ isLoading: false, sessionVerified: true });
            return { error: authError };
          }

          // Sync user data after login with timeout
          try {
            console.log("[Auth] loginWithSupabase: Calling syncWithSupabase...");
            await withTimeout(get().syncWithSupabase(), 20000, "User sync");
            console.log("[Auth] loginWithSupabase: syncWithSupabase completed");
          } catch (syncError) {
            console.error("[Auth] Sync after login failed:", syncError);
            // Login succeeded but sync failed - return error so login page can handle it
            set({
              isLoading: false,
              isAuthenticated: false,
              sessionVerified: true,
              user: null,
              organization: null,
              location: null,
            });
            return { error: new Error("Login succeeded but failed to load your account. Please try again.") };
          }

          console.log("[Auth] loginWithSupabase: SUCCESS");
          return { error: null };
        } catch (error) {
          console.error("[Auth] Login error:", error);
          set({ isLoading: false, sessionVerified: true });
          return {
            error: error instanceof Error
              ? error
              : new Error("Login failed. Please try again.")
          };
        }
      },

      signUpWithSupabase: async (email: string, password: string, name: string, orgName: string) => {
        set({ isLoading: true });
        const supabase = getSupabaseClient();

        // 1. Create auth user
        const { data: authData, error: authError } = await supabase.auth.signUp({
          email,
          password,
        });

        if (authError || !authData.user) {
          set({ isLoading: false });
          return { error: authError };
        }

        // 2. Create organization
        const orgSlug = orgName.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "");
        const { data: orgData, error: orgError } = await supabase
          .from("organizations")
          .insert({ name: orgName, slug: `${orgSlug}-${Date.now()}` })
          .select()
          .single();

        if (orgError || !orgData) {
          set({ isLoading: false });
          return { error: orgError };
        }

        // 3. Create user profile
        const { error: profileError } = await supabase
          .from("users")
          .insert({
            auth_id: authData.user.id,
            email,
            name,
            organization_id: orgData.id,
            role: "OWNER",
          });

        if (profileError) {
          set({ isLoading: false });
          return { error: profileError };
        }

        // 4. Create default location
        await supabase
          .from("locations")
          .insert({
            organization_id: orgData.id,
            name: "Main Location",
          });

        // 5. Create organization settings
        await supabase
          .from("organization_settings")
          .insert({ organization_id: orgData.id });

        await get().syncWithSupabase();
        return { error: null };
      },

      logout: async () => {
        const { useSupabase, isPinAuth } = get();
        if (useSupabase && !isPinAuth) {
          const supabase = getSupabaseClient();
          await supabase.auth.signOut();
        }
        // Keep storeConfig when logging out - only clear user session
        set({
          user: null,
          organization: null,
          location: null,
          isAuthenticated: false,
          isLoading: false,
          sessionVerified: false,
          isPlatformAdmin: false,
          platformAdmin: null,
          impersonation: null,
          isPartnerUser: false,
          partnerUser: null,
          partner: null,
          isPinAuth: false,
        });
      },

      // Logout user but keep store config (for PIN switching between users)
      logoutUser: () => {
        set({
          user: null,
          organization: null,
          location: null,
          isAuthenticated: false,
          isLoading: false,
          sessionVerified: false,
          isPlatformAdmin: false,
          platformAdmin: null,
          impersonation: null,
          isPartnerUser: false,
          partnerUser: null,
          partner: null,
          isPinAuth: false,
        });
      },

      // Store configuration management
      setStoreConfig: (config) => {
        set({ storeConfig: config });
      },

      clearStoreConfig: () => {
        set({
          storeConfig: null,
          user: null,
          organization: null,
          location: null,
          isAuthenticated: false,
          sessionVerified: false,
          isPinAuth: false,
        });
      },

      // PIN-based login
      loginWithPin: (storeCode, pin, result) => {
        const { user: userData, organization: org, organizationSettings: settings, location: loc, employee } = result;

        const user: User = {
          id: userData.id,
          email: userData.email,
          name: userData.name,
          role: userData.role as UserRole,
          organizationId: org.id,
          locationId: loc?.id || "",
          employeeId: employee.id,
          // PIN intentionally NOT stored on user object - security risk if persisted to localStorage
        };

        const organization: Organization = {
          id: org.id,
          name: org.name,
          slug: org.slug,
          logo: org.logo || undefined,
          taxRate: settings?.tax_rate ?? 0,
          taxInclusive: settings?.tax_inclusive ?? false,
          currency: settings?.currency ?? "USD",
          timezone: settings?.timezone ?? "America/New_York",
          settings: settings ? {
            currency: settings.currency ?? "USD",
            timezone: settings.timezone ?? "America/New_York",
            taxRate: settings.tax_rate ?? 0,
            taxInclusive: settings.tax_inclusive ?? false,
            receiptHeader: settings.receipt_header ?? undefined,
            receiptFooter: settings.receipt_footer ?? undefined,
            showLogo: settings.show_logo ?? true,
            requirePin: settings.require_pin ?? false,
            allowNegative: settings.allow_negative ?? false,
            defaultTipPercentages: settings.default_tip_percentages ?? [15, 18, 20, 25],
          } : undefined,
        };

        const location: Location | null = loc ? {
          id: loc.id,
          name: loc.name,
          address: loc.address || undefined,
        } : null;

        const storeConfig: StoreConfig = {
          id: org.id,
          name: org.name,
          code: org.slug,
          logo: org.logo || undefined,
        };

        set({
          user,
          organization,
          location,
          storeConfig,
          isAuthenticated: true,
          isLoading: false,
          sessionVerified: true, // PIN auth is verified immediately
          isPinAuth: true,
          useSupabase: true,
        });
      },

      switchLocation: (location) => {
        set({ location });
      },

      updateUser: (updates) => {
        const currentUser = get().user;
        if (currentUser) {
          set({ user: { ...currentUser, ...updates } });
        }
      },

      hasPermission: (permission) => {
        const user = get().user;
        if (!user) return false;
        return hasPermission(user.role, permission);
      },

      hasAnyPermission: (permissions) => {
        const user = get().user;
        if (!user) return false;
        return permissions.some((p) => hasPermission(user.role, p));
      },

      // Partner permission helpers
      checkPartnerPermission: (permission) => {
        const { partnerUser } = get();
        if (!partnerUser) return false;
        return hasPartnerPermission(partnerUser.role, permission);
      },

      hasAnyPartnerPermission: (permissions) => {
        const { partnerUser } = get();
        if (!partnerUser) return false;
        return permissions.some((p) => hasPartnerPermission(partnerUser.role, p));
      },

      setLoading: (loading) => {
        set({ isLoading: loading });
      },

      syncWithSupabase: async () => {
        console.log("[Auth] syncWithSupabase: START");

        // Helper to add timeout to promises
        const withTimeout = <T>(promise: Promise<T>, ms: number, name: string): Promise<T> => {
          return Promise.race([
            promise,
            new Promise<T>((_, reject) =>
              setTimeout(() => reject(new Error(`${name} timed out after ${ms}ms`)), ms)
            )
          ]);
        };

        try {
          const supabase = getSupabaseClient();
          console.log("[Auth] syncWithSupabase: Got Supabase client");

          // Wait for the Supabase client to finish restoring its session from localStorage.
          // Without this, RLS queries may fail because auth.uid() is still null.
          // getSession() returns the locally cached session (fast), ensuring the client is ready.
          await withTimeout(supabase.auth.getSession(), 5000, "getSession");
          console.log("[Auth] syncWithSupabase: Session ready, calling getUser()...");

          // getUser() verifies the session with the server (authoritative)
          const { data: { user: authUser }, error: authError } = await withTimeout(
            supabase.auth.getUser(),
            10000,
            "getUser"
          );
          console.log("[Auth] syncWithSupabase: getUser() returned", { hasUser: !!authUser, authError: authError?.message });

          if (authError) {
            console.error("[Auth] syncWithSupabase: getUser error:", authError);
            set({ isLoading: false, isAuthenticated: false, sessionVerified: true, isPlatformAdmin: false, platformAdmin: null, isPartnerUser: false, partnerUser: null, partner: null, user: null, organization: null, location: null });
            return;
          }

          if (!authUser) {
            // No auth session - clear everything including stale org/user data
            console.log("[Auth] syncWithSupabase: No auth user, setting sessionVerified=true");
            set({ isLoading: false, isAuthenticated: false, sessionVerified: true, isPlatformAdmin: false, platformAdmin: null, isPartnerUser: false, partnerUser: null, partner: null, user: null, organization: null, location: null });
            return;
          }

          console.log("[Auth] syncWithSupabase: Auth user found, querying platform_admins, partner_users, users...");
          // Check platform admin, partner user, and user profile in parallel with timeout
          // Use .maybeSingle() instead of .single() because the row might not exist
          // (e.g., a regular user won't have a platform_admins or partner_users row)
          const [platformAdminResult, partnerUserResult, profileResult] = await withTimeout(
            Promise.all([
              supabase
                .from("platform_admins")
                .select("*")
                .eq("auth_id", authUser.id)
                .eq("is_active", true)
                .maybeSingle(),
              supabase
                .from("partner_users")
                .select("*, partner:partners(*)")
                .eq("auth_id", authUser.id)
                .eq("is_active", true)
                .maybeSingle(),
              supabase
                .from("users")
                .select("*")
                .eq("auth_id", authUser.id)
                .maybeSingle(),
            ]),
            30000,
            "user lookup queries"
          );

        const platformAdminData = platformAdminResult.data;
        const partnerUserData = partnerUserResult.data;
        const profile = profileResult.data;

        // Debug logging for auth issues
        if (process.env.NODE_ENV === "development" || true) {
          console.log("[Auth] syncWithSupabase results:", {
            hasAuthUser: !!authUser,
            authUserId: authUser?.id,
            platformAdminData: !!platformAdminData,
            platformAdminError: platformAdminResult.error?.message,
            partnerUserData: !!partnerUserData,
            partnerUserError: partnerUserResult.error?.message,
            profile: !!profile,
            profileError: profileResult.error?.message,
          });
        }

        if (platformAdminData) {
          // User is a platform admin - set state and skip regular user flow
          set({
            isPlatformAdmin: true,
            platformAdmin: {
              id: platformAdminData.id,
              email: platformAdminData.email,
              name: platformAdminData.name,
            },
            isAuthenticated: true,
            isLoading: false,
            sessionVerified: true, // Session verified after successful Supabase auth
            useSupabase: true,
            user: null,
            organization: null,
            location: null,
            isPartnerUser: false,
            partnerUser: null,
            partner: null,
          });
          return;
        }

        if (partnerUserData) {
          // User is a partner user - set state and skip regular user flow
          const partnerData = partnerUserData.partner as unknown as {
            id: string;
            name: string;
            slug: string;
            logo: string | null;
            default_pos_name: string | null;
            primary_color: string | null;
            secondary_color: string | null;
            status: string;
          };

          // Partner user but partner is not active - sign out and return
          if (!partnerData || partnerData.status !== "ACTIVE") {
            console.warn("[Auth] syncWithSupabase: Partner user but partner is not active:", partnerData?.status);
            try {
              await supabase.auth.signOut();
            } catch (e) {
              console.error("[Auth] Failed to sign out inactive partner user:", e);
            }
            set({
              isAuthenticated: false,
              isLoading: false,
              sessionVerified: true,
              isPartnerUser: false,
              partnerUser: null,
              partner: null,
              isPlatformAdmin: false,
              platformAdmin: null,
              user: null,
              organization: null,
              location: null,
            });
            return;
          }

          // Partner is active - set authenticated state
          if (partnerData && partnerData.status === "ACTIVE") {
            set({
              isPartnerUser: true,
              partnerUser: {
                id: partnerUserData.id,
                email: partnerUserData.email,
                name: partnerUserData.name,
                role: partnerUserData.role as PartnerUserRole,
                partnerId: partnerUserData.partner_id,
              },
              partner: {
                id: partnerData.id,
                name: partnerData.name,
                slug: partnerData.slug,
                logo: partnerData.logo || undefined,
                defaultPosName: partnerData.default_pos_name || undefined,
                primaryColor: partnerData.primary_color || undefined,
                secondaryColor: partnerData.secondary_color || undefined,
              },
              isAuthenticated: true,
              isLoading: false,
              sessionVerified: true,
              useSupabase: true,
              user: null,
              organization: null,
              location: null,
              isPlatformAdmin: false,
              platformAdmin: null,
            });
            return;
          }
        }

        if (!profile) {
          // No user profile found - this is a zombie session (auth exists but no profile)
          // This happens when:
          // 1. User was deleted from the users table
          // 2. RLS policies prevent access
          // 3. User is only a partner/admin but those queries failed
          // Clear the session to prevent infinite redirect loops
          console.warn("[Auth] syncWithSupabase: Zombie session detected - auth user exists but no profile found. Clearing session.");
          try {
            await supabase.auth.signOut();
          } catch (signOutError) {
            console.error("[Auth] Failed to sign out zombie session:", signOutError);
          }
          set({
            isLoading: false,
            isAuthenticated: false,
            sessionVerified: true,
            isPlatformAdmin: false,
            platformAdmin: null,
            isPartnerUser: false,
            partnerUser: null,
            partner: null,
            user: null,
            organization: null,
            location: null,
          });
          return;
        }

        // Fetch organization, settings, and location in parallel with timeout
        // Use .maybeSingle() to gracefully handle missing data
        const [orgResult, orgSettingsResult, locationsResult] = await withTimeout(
          Promise.all([
            supabase
              .from("organizations")
              .select("*")
              .eq("id", profile.organization_id)
              .maybeSingle(),
            supabase
              .from("organization_settings")
              .select("*")
              .eq("organization_id", profile.organization_id)
              .maybeSingle(),
            supabase
              .from("locations")
              .select("*")
              .eq("organization_id", profile.organization_id)
              .limit(1),
          ]),
          30000,
          "org lookup queries"
        );

        const org = orgResult.data;
        const orgSettings = orgSettingsResult.data;
        const location = locationsResult.data?.[0];

        const user: User = {
          id: profile.id,
          email: profile.email,
          name: profile.name,
          role: profile.role as UserRole,
          organizationId: profile.organization_id,
          locationId: location?.id || "",
          employeeId: profile.id,
        };

        const organization: Organization | null = org ? {
          id: org.id,
          name: org.name,
          slug: org.slug,
          logo: org.logo || undefined,
          taxRate: orgSettings?.tax_rate ?? 825, // Default 8.25%
          taxInclusive: orgSettings?.tax_inclusive ?? false,
          currency: orgSettings?.currency ?? "USD",
          timezone: orgSettings?.timezone ?? "America/New_York",
          settings: orgSettings ? {
            currency: orgSettings.currency ?? "USD",
            timezone: orgSettings.timezone ?? "America/New_York",
            taxRate: orgSettings.tax_rate ?? 825,
            taxInclusive: orgSettings.tax_inclusive ?? false,
            receiptHeader: orgSettings.receipt_header ?? undefined,
            receiptFooter: orgSettings.receipt_footer ?? undefined,
            showLogo: orgSettings.show_logo ?? true,
            requirePin: orgSettings.require_pin ?? false,
            allowNegative: orgSettings.allow_negative ?? false,
            defaultTipPercentages: orgSettings.default_tip_percentages ?? [15, 18, 20, 25],
          } : undefined,
        } : null;

        const loc: Location | null = location ? {
          id: location.id,
          name: location.name,
          address: location.address || undefined,
        } : null;

        console.log("[Auth] syncWithSupabase: Regular user authenticated successfully");
        set({
          user,
          organization,
          location: loc,
          isAuthenticated: true,
          isLoading: false,
          sessionVerified: true, // Session verified after successful Supabase auth
          useSupabase: true, // Supabase mode - enable realtime
        });
        } catch (error) {
          console.error("[Auth] syncWithSupabase: CAUGHT ERROR", error);
          // On any error, clear ALL state to prevent stale data
          set({
            isLoading: false,
            isAuthenticated: false,
            sessionVerified: true,
            isPlatformAdmin: false,
            platformAdmin: null,
            isPartnerUser: false,
            partnerUser: null,
            partner: null,
            user: null,
            organization: null,
            location: null,
          });
        }
      },
    }),
    {
      name: "banger-pos-auth",
      partialize: (state) => ({
        user: state.user ? { ...state.user, pin: undefined } : null,
        organization: state.organization,
        location: state.location,
        isAuthenticated: state.isAuthenticated,
        useSupabase: state.useSupabase,
        // isPlatformAdmin, platformAdmin NOT persisted — always derived fresh from Supabase
        // isPartnerUser, partnerUser, partner NOT persisted — always derived fresh
        impersonation: state.impersonation,
        storeConfig: state.storeConfig,
        isPinAuth: state.isPinAuth,
      }),
      onRehydrateStorage: () => (state) => {
        // Set loading to false after hydration completes
        if (state) {
          state.setLoading(false);
        }
      },
    }
  )
);
