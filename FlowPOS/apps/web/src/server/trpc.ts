import { initTRPC, TRPCError } from "@trpc/server";
import superjson from "superjson";
import { ZodError } from "zod";
import { createDb, createAdminDb, type SupabaseClient } from "./db";
import type { Database } from "@pos/db";
import type { SupabaseClient as SupabaseAdminClient } from "@supabase/supabase-js";
import {
  type Permission,
  type UserRole,
  hasPermission,
  hasAnyPermission,
} from "@/lib/permissions";

type UserProfile = Database["public"]["Tables"]["users"]["Row"];

/**
 * Context for tRPC procedures
 */
export interface Context {
  db: SupabaseClient;
  user: UserProfile | null;
  organizationId: string | null;
  clientIp: string;
}

// Request-scoped cache for user profiles to avoid duplicate queries
const userProfileCache = new Map<string, { profile: UserProfile | null; timestamp: number }>();
const PROFILE_CACHE_TTL = 30 * 1000; // 30 seconds

/**
 * Creates context for each request
 * Supports both Supabase session auth (via Authorization header) and PIN auth (via custom headers)
 */
export async function createContext(opts?: { req?: Request }): Promise<Context> {
  // Extract client IP from request headers
  let clientIp = "unknown";
  if (opts?.req) {
    const headers = opts.req.headers;
    clientIp =
      headers.get("cf-connecting-ip") ||
      headers.get("x-real-ip") ||
      headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
      "unknown";
  }

  const authHeader = opts?.req?.headers.get("authorization");
  const pinUserId = opts?.req?.headers.get("x-pin-user-id");
  const pinOrgId = opts?.req?.headers.get("x-pin-org-id");

  let user: UserProfile | null = null;
  let organizationId: string | null = null;

  // --- PIN Auth Path: look up user by ID using admin client ---
  if (pinUserId && pinOrgId) {
    const db = createAdminDb();
    const now = Date.now();
    const cacheKey = `pin:${pinUserId}`;
    const cached = userProfileCache.get(cacheKey);

    if (cached && (now - cached.timestamp) < PROFILE_CACHE_TTL) {
      user = cached.profile;
      organizationId = cached.profile?.organization_id ?? null;
    } else {
      const { data: profile } = await db
        .from("users")
        .select("*")
        .eq("id", pinUserId)
        .eq("organization_id", pinOrgId)
        .single();

      if (profile) {
        user = profile as UserProfile;
        organizationId = profile.organization_id;
      }
      userProfileCache.set(cacheKey, { profile: user, timestamp: now });
    }

    return { db, user, organizationId, clientIp };
  }

  // --- Supabase Auth Path: use access token ---
  const db = await createDb(authHeader?.replace("Bearer ", ""));

  if (authHeader) {
    const { data: { user: authUser } } = await db.auth.getUser();

    if (authUser) {
      const cacheKey = authUser.id;
      const cached = userProfileCache.get(cacheKey);
      const now = Date.now();

      if (cached && (now - cached.timestamp) < PROFILE_CACHE_TTL) {
        user = cached.profile;
        organizationId = cached.profile?.organization_id ?? null;
      } else {
        const { data: profile } = await db
          .from("users")
          .select("id, auth_id, organization_id, email, name, role, is_active")
          .eq("auth_id", authUser.id)
          .single();

        if (profile) {
          user = profile as UserProfile;
          organizationId = profile.organization_id;
        }
        userProfileCache.set(cacheKey, { profile: user, timestamp: now });
      }
    }
  }

  // Cleanup old cache entries periodically
  if (userProfileCache.size > 100) {
    const cutoff = Date.now() - PROFILE_CACHE_TTL;
    for (const [key, value] of userProfileCache.entries()) {
      if (value.timestamp < cutoff) {
        userProfileCache.delete(key);
      }
    }
  }

  return { db, user, organizationId, clientIp };
}

/**
 * Initialize tRPC
 */
const t = initTRPC.context<Context>().create({
  transformer: superjson,
  errorFormatter({ shape, error }) {
    return {
      ...shape,
      data: {
        ...shape.data,
        zodError:
          error.cause instanceof ZodError ? error.cause.flatten() : null,
      },
    };
  },
});

/**
 * Export reusable router and procedure helpers
 */
export const router = t.router;
export const publicProcedure = t.procedure;
export const createCallerFactory = t.createCallerFactory;

/**
 * Middleware to check if user is authenticated
 */
const isAuthed = t.middleware(async ({ ctx, next }) => {
  if (!ctx.user || !ctx.organizationId) {
    throw new TRPCError({
      code: "UNAUTHORIZED",
      message: "You must be logged in to access this resource",
    });
  }

  return next({
    ctx: {
      user: ctx.user,
      organizationId: ctx.organizationId,
    },
  });
});

/**
 * Protected procedure - requires authentication
 */
export const protectedProcedure = t.procedure.use(isAuthed);

/**
 * Middleware to check for specific roles
 */
const hasRole = (allowedRoles: Database["public"]["Enums"]["user_role"][]) =>
  t.middleware(async ({ ctx, next }) => {
    if (!ctx.user || !ctx.organizationId) {
      throw new TRPCError({
        code: "UNAUTHORIZED",
        message: "You must be logged in to access this resource",
      });
    }

    if (!ctx.user.role || !allowedRoles.includes(ctx.user.role)) {
      throw new TRPCError({
        code: "FORBIDDEN",
        message: "You do not have permission to access this resource",
      });
    }

    return next({
      ctx: {
        user: ctx.user,
        organizationId: ctx.organizationId,
      },
    });
  });

/**
 * Admin procedure - requires OWNER, ADMIN, or MANAGER role
 */
export const adminProcedure = t.procedure.use(
  hasRole(["OWNER", "ADMIN", "MANAGER"])
);

/**
 * Owner procedure - requires OWNER or ADMIN role
 */
export const ownerProcedure = t.procedure.use(hasRole(["OWNER", "ADMIN"]));

/**
 * Middleware to check for specific permission
 */
const requiresPermission = (permission: Permission) =>
  t.middleware(async ({ ctx, next }) => {
    if (!ctx.user || !ctx.organizationId) {
      throw new TRPCError({
        code: "UNAUTHORIZED",
        message: "You must be logged in to access this resource",
      });
    }

    const userRole = ctx.user.role as UserRole;
    if (!hasPermission(userRole, permission)) {
      throw new TRPCError({
        code: "FORBIDDEN",
        message: `You do not have the required permission: ${permission}`,
      });
    }

    return next({
      ctx: {
        user: ctx.user,
        organizationId: ctx.organizationId,
      },
    });
  });

/**
 * Middleware to check for any of the specified permissions
 */
const requiresAnyPermission = (permissions: Permission[]) =>
  t.middleware(async ({ ctx, next }) => {
    if (!ctx.user || !ctx.organizationId) {
      throw new TRPCError({
        code: "UNAUTHORIZED",
        message: "You must be logged in to access this resource",
      });
    }

    const userRole = ctx.user.role as UserRole;
    if (!hasAnyPermission(userRole, permissions)) {
      throw new TRPCError({
        code: "FORBIDDEN",
        message: `You need one of the following permissions: ${permissions.join(", ")}`,
      });
    }

    return next({
      ctx: {
        user: ctx.user,
        organizationId: ctx.organizationId,
      },
    });
  });

/**
 * Create a procedure that requires a specific permission
 */
export const createPermissionProcedure = (permission: Permission) =>
  t.procedure.use(requiresPermission(permission));

/**
 * Create a procedure that requires any of the specified permissions
 */
export const createAnyPermissionProcedure = (permissions: Permission[]) =>
  t.procedure.use(requiresAnyPermission(permissions));

// Pre-defined permission procedures for common operations
export const posProcedure = createPermissionProcedure("pos:access");
export const productViewProcedure = createPermissionProcedure("products:view");
export const productEditProcedure = createPermissionProcedure("products:edit");
export const productDeleteProcedure = createPermissionProcedure("products:delete");
export const orderViewProcedure = createPermissionProcedure("orders:view");
export const orderCreateProcedure = createPermissionProcedure("orders:create");
export const orderEditProcedure = createPermissionProcedure("orders:edit");
export const inventoryViewProcedure = createPermissionProcedure("inventory:view");
export const inventoryAdjustProcedure = createPermissionProcedure("inventory:adjust");
export const customerViewProcedure = createPermissionProcedure("customers:view");
export const customerEditProcedure = createPermissionProcedure("customers:edit");
export const employeeViewProcedure = createPermissionProcedure("employees:view");
export const employeeEditProcedure = createPermissionProcedure("employees:edit");
export const reportViewProcedure = createPermissionProcedure("reports:view");
export const tableViewProcedure = createPermissionProcedure("tables:view");
export const tableManageProcedure = createPermissionProcedure("tables:manage");
export const kitchenViewProcedure = createPermissionProcedure("kitchen:view");
export const kitchenBumpProcedure = createPermissionProcedure("kitchen:bump");
export const settingsViewProcedure = createPermissionProcedure("settings:view");
export const settingsEditProcedure = createPermissionProcedure("settings:edit");
export const loyaltyViewProcedure = createPermissionProcedure("loyalty:view");
export const loyaltyManageProcedure = createPermissionProcedure("loyalty:manage");

// ============================================================================
// Platform Admin Procedures
// ============================================================================

type PlatformAdmin = Database["public"]["Tables"]["platform_admins"]["Row"];

export interface PlatformAdminContext extends Context {
  platformAdmin: PlatformAdmin;
  adminDb: SupabaseAdminClient<Database>;
}

/**
 * Middleware to check if user is a platform admin
 * Platform admins are separate from organization users and have cross-org access
 */
const isPlatformAdmin = t.middleware(async ({ ctx, next }) => {
  // Get the auth user
  const {
    data: { user: authUser },
  } = await ctx.db.auth.getUser();

  if (!authUser) {
    throw new TRPCError({
      code: "UNAUTHORIZED",
      message: "You must be logged in to access this resource",
    });
  }

  // Create admin client with service role key (bypasses RLS)
  const adminDb = createAdminDb();

  // Check if user is a platform admin using admin client (bypasses RLS)
  const { data: platformAdmin } = await adminDb
    .from("platform_admins")
    .select("*")
    .eq("auth_id", authUser.id)
    .eq("is_active", true)
    .single();

  if (!platformAdmin) {
    throw new TRPCError({
      code: "FORBIDDEN",
      message: "Platform admin access required",
    });
  }

  return next({
    ctx: {
      ...ctx,
      platformAdmin,
      adminDb,
    },
  });
});

/**
 * Platform admin procedure - requires platform admin authentication
 * Use this for all platform-level operations (org management, signup approvals, etc.)
 */
export const platformAdminProcedure = t.procedure.use(isPlatformAdmin);

/**
 * Helper to log platform admin actions for audit trail
 * Accepts either regular SupabaseClient or admin SupabaseClient
 */
export async function logPlatformAdminAction(
  db: SupabaseClient | SupabaseAdminClient<Database>,
  adminId: string,
  action: string,
  targetType: string,
  targetId: string,
  details?: Record<string, unknown>,
  ipAddress?: string
) {
  await db.from("platform_audit_logs").insert({
    admin_id: adminId,
    action,
    target_type: targetType,
    target_id: targetId,
    details: details ? JSON.parse(JSON.stringify(details)) : null,
    ip_address: ipAddress ?? null,
  });
}

// ============================================================================
// Partner Procedures
// ============================================================================

type Partner = Database["public"]["Tables"]["partners"]["Row"];
type PartnerUser = Database["public"]["Tables"]["partner_users"]["Row"];

export interface PartnerContext extends Context {
  partner: Partner;
  partnerUser: PartnerUser;
  adminDb: SupabaseAdminClient<Database>;
}

/**
 * Middleware to check if user is a partner user
 * Partner users can manage organizations under their partner umbrella
 */
const isPartnerUser = t.middleware(async ({ ctx, next }) => {
  // Get the auth user
  const {
    data: { user: authUser },
  } = await ctx.db.auth.getUser();

  if (!authUser) {
    throw new TRPCError({
      code: "UNAUTHORIZED",
      message: "You must be logged in to access this resource",
    });
  }

  // Create admin client with service role key (bypasses RLS)
  const adminDb = createAdminDb();

  // Check if user is a partner user
  const { data: partnerUser } = await adminDb
    .from("partner_users")
    .select("*, partner:partners(*)")
    .eq("auth_id", authUser.id)
    .eq("is_active", true)
    .single();

  if (!partnerUser) {
    throw new TRPCError({
      code: "FORBIDDEN",
      message: "Partner access required",
    });
  }

  const partner = partnerUser.partner as unknown as Partner;

  if (!partner || partner.status !== "ACTIVE") {
    throw new TRPCError({
      code: "FORBIDDEN",
      message: "Partner account is not active",
    });
  }

  // Update last login
  await adminDb
    .from("partner_users")
    .update({ last_login_at: new Date().toISOString() })
    .eq("id", partnerUser.id);

  return next({
    ctx: {
      ...ctx,
      partner,
      partnerUser: {
        ...partnerUser,
        partner: undefined, // Remove nested partner to avoid duplication
      } as PartnerUser,
      adminDb,
    },
  });
});

/**
 * Partner procedure - requires partner user authentication
 * Use this for all partner-level operations (org management, branding, etc.)
 */
export const partnerProcedure = t.procedure.use(isPartnerUser);

/**
 * Helper to log partner actions for audit trail
 */
export async function logPartnerAction(
  db: SupabaseClient | SupabaseAdminClient<Database>,
  partnerId: string,
  userId: string,
  action: string,
  targetType: string,
  targetId: string,
  details?: Record<string, unknown>,
  ipAddress?: string
) {
  await db.from("partner_audit_logs").insert({
    partner_id: partnerId,
    user_id: userId,
    action,
    target_type: targetType,
    target_id: targetId,
    details: details ? JSON.parse(JSON.stringify(details)) : null,
    ip_address: ipAddress ?? null,
  });
}
