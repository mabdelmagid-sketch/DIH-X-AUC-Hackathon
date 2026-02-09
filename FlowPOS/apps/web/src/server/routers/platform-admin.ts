import { z } from "zod";
import { TRPCError } from "@trpc/server";
import bcrypt from "bcryptjs";
import {
  router,
  publicProcedure,
  platformAdminProcedure,
  logPlatformAdminAction,
} from "../trpc";

const BCRYPT_ROUNDS = 10;

/**
 * Platform Admin Router
 *
 * Handles all platform-level operations:
 * - Organization management (list, suspend, activate, delete)
 * - Signup request approvals
 * - Impersonation for support
 * - Audit log viewing
 */
export const platformAdminRouter = router({
  /**
   * Get current platform admin profile
   */
  me: platformAdminProcedure.query(async ({ ctx }) => {
    return ctx.platformAdmin;
  }),

  /**
   * Check if user is a platform admin (public - used for UI routing)
   */
  checkAccess: publicProcedure.query(async ({ ctx }) => {
    const {
      data: { user: authUser },
    } = await ctx.db.auth.getUser();

    if (!authUser) {
      return { isPlatformAdmin: false };
    }

    const { data: platformAdmin } = await ctx.db
      .from("platform_admins")
      .select("id")
      .eq("auth_id", authUser.id)
      .eq("is_active", true)
      .single();

    return { isPlatformAdmin: !!platformAdmin };
  }),

  // ============================================================================
  // Organization Management
  // ============================================================================
  organizations: router({
    /**
     * List all organizations with optional filters
     */
    list: platformAdminProcedure
      .input(
        z.object({
          status: z.enum(["PENDING", "ACTIVE", "SUSPENDED"]).optional(),
          search: z.string().optional(),
          limit: z.number().min(1).max(100).default(50),
          offset: z.number().min(0).default(0),
        })
      )
      .query(async ({ ctx, input }) => {
        // Use adminDb to bypass RLS and see all organizations
        let query = ctx.adminDb
          .from("organizations")
          .select(
            `
            *,
            users:users(count),
            locations:locations(count),
            orders:orders(count)
          `,
            { count: "exact" }
          )
          .order("created_at", { ascending: false })
          .range(input.offset, input.offset + input.limit - 1);

        if (input.status) {
          query = query.eq("status", input.status);
        }

        if (input.search) {
          query = query.or(
            `name.ilike.%${input.search}%,slug.ilike.%${input.search}%`
          );
        }

        const { data, error, count } = await query;

        if (error) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: "Failed to fetch organizations",
          });
        }

        return {
          organizations: data ?? [],
          total: count ?? 0,
        };
      }),

    /**
     * Get organization by ID with full details
     */
    getById: platformAdminProcedure
      .input(z.object({ id: z.string() }))
      .query(async ({ ctx, input }) => {
        // Use adminDb to bypass RLS
        const { data: org, error } = await ctx.adminDb
          .from("organizations")
          .select(
            `
            *,
            settings:organization_settings(*),
            locations:locations(*),
            users:users(id, name, email, role, is_active, created_at)
          `
          )
          .eq("id", input.id)
          .single();

        if (error || !org) {
          throw new TRPCError({
            code: "NOT_FOUND",
            message: "Organization not found",
          });
        }

        // Get order stats using adminDb
        const { count: orderCount } = await ctx.adminDb
          .from("orders")
          .select("*", { count: "exact", head: true })
          .eq("organization_id", input.id);

        const { data: recentOrders } = await ctx.adminDb
          .from("orders")
          .select("total, created_at")
          .eq("organization_id", input.id)
          .order("created_at", { ascending: false })
          .limit(30);

        const totalRevenue =
          recentOrders?.reduce((sum, o) => sum + (o.total ?? 0), 0) ?? 0;

        return {
          ...org,
          stats: {
            totalOrders: orderCount ?? 0,
            recentRevenue: totalRevenue,
          },
        };
      }),

    /**
     * Suspend an organization
     */
    suspend: platformAdminProcedure
      .input(
        z.object({
          id: z.string(),
          reason: z.string().min(10, "Reason must be at least 10 characters"),
        })
      )
      .mutation(async ({ ctx, input }) => {
        // Use adminDb to bypass RLS
        const { data: org, error } = await ctx.adminDb
          .from("organizations")
          .update({
            status: "SUSPENDED",
            suspended_at: new Date().toISOString(),
            suspended_reason: input.reason,
          })
          .eq("id", input.id)
          .select()
          .single();

        if (error) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: "Failed to suspend organization",
          });
        }

        // Log the action
        await logPlatformAdminAction(
          ctx.adminDb,
          ctx.platformAdmin.id,
          "SUSPEND_ORGANIZATION",
          "organization",
          input.id,
          { reason: input.reason },
          ctx.clientIp
        );

        return org;
      }),

    /**
     * Activate a suspended organization
     */
    activate: platformAdminProcedure
      .input(z.object({ id: z.string() }))
      .mutation(async ({ ctx, input }) => {
        // Use adminDb to bypass RLS
        const { data: org, error } = await ctx.adminDb
          .from("organizations")
          .update({
            status: "ACTIVE",
            suspended_at: null,
            suspended_reason: null,
          })
          .eq("id", input.id)
          .select()
          .single();

        if (error) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: "Failed to activate organization",
          });
        }

        // Log the action
        await logPlatformAdminAction(
          ctx.adminDb,
          ctx.platformAdmin.id,
          "ACTIVATE_ORGANIZATION",
          "organization",
          input.id,
          {},
          ctx.clientIp
        );

        return org;
      }),

    /**
     * Delete an organization (dangerous - requires confirmation)
     */
    delete: platformAdminProcedure
      .input(
        z.object({
          id: z.string(),
          confirmation: z.literal("DELETE"),
        })
      )
      .mutation(async ({ ctx, input }) => {
        // Get org details before deletion for logging using adminDb
        const { data: org } = await ctx.adminDb
          .from("organizations")
          .select("name, slug")
          .eq("id", input.id)
          .single();

        // Delete organization using adminDb (cascade will handle related records)
        const { error } = await ctx.adminDb
          .from("organizations")
          .delete()
          .eq("id", input.id);

        if (error) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: "Failed to delete organization",
          });
        }

        // Log the action
        await logPlatformAdminAction(
          ctx.adminDb,
          ctx.platformAdmin.id,
          "DELETE_ORGANIZATION",
          "organization",
          input.id,
          { name: org?.name, slug: org?.slug },
          ctx.clientIp
        );

        return { success: true };
      }),

    /**
     * Create a new organization directly (bypass signup flow)
     */
    create: platformAdminProcedure
      .input(
        z.object({
          name: z.string().min(2),
          ownerEmail: z.string().email(),
          ownerName: z.string().min(2),
          ownerPassword: z.string().min(8),
          // White-label branding
          posName: z.string().min(2).default("Banger POS"),
          posLogo: z.string().url().optional(),
          // Plan
          plan: z.enum(["free", "pro", "enterprise"]).default("free"),
        })
      )
      .mutation(async ({ ctx, input }) => {
        // Generate slug
        const slug = `${input.name
          .toLowerCase()
          .replace(/\s+/g, "-")
          .replace(/[^a-z0-9-]/g, "")}-${Date.now()}`;

        // Create Supabase auth user using admin client (requires service role key)
        const { data: authData, error: authError } =
          await ctx.adminDb.auth.admin.createUser({
            email: input.ownerEmail,
            password: input.ownerPassword,
            email_confirm: true,
          });

        if (authError || !authData.user) {
          throw new TRPCError({
            code: "BAD_REQUEST",
            message: authError?.message ?? "Failed to create user",
          });
        }

        // Create organization using admin client (bypasses RLS)
        const { data: org, error: orgError } = await ctx.adminDb
          .from("organizations")
          .insert({
            name: input.name,
            slug,
            status: "ACTIVE",
          })
          .select()
          .single();

        if (orgError || !org) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: "Failed to create organization",
          });
        }

        // Create user profile using admin client
        const { data: user, error: userError } = await ctx.adminDb
          .from("users")
          .insert({
            auth_id: authData.user.id,
            email: input.ownerEmail,
            name: input.ownerName,
            organization_id: org.id,
            role: "OWNER",
          })
          .select()
          .single();

        if (userError || !user) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: "Failed to create user profile",
          });
        }

        // Create default location using admin client
        const { data: location } = await ctx.adminDb
          .from("locations")
          .insert({
            name: "Main Location",
            organization_id: org.id,
          })
          .select()
          .single();

        // Create employee record using admin client
        if (location) {
          await ctx.adminDb.from("employees").insert({
            user_id: user.id,
            location_id: location.id,
          });
        }

        // Get AI credits limit based on plan
        const aiCreditsLimit = input.plan === "enterprise" ? 1000 : input.plan === "pro" ? 100 : 0;
        const aiCreditsResetAt = new Date();
        aiCreditsResetAt.setMonth(aiCreditsResetAt.getMonth() + 1);

        // Create default settings with white-label and plan fields using admin client
        await ctx.adminDb.from("organization_settings").insert({
          organization_id: org.id,
          currency: "USD",
          timezone: "America/New_York",
          tax_rate: 0,
          tax_inclusive: false,
          // White-label branding
          pos_name: input.posName,
          pos_logo: input.posLogo || null,
          // Plan/credits
          plan: input.plan,
          ai_credits_used: 0,
          ai_credits_limit: aiCreditsLimit,
          ai_credits_reset_at: aiCreditsResetAt.toISOString(),
        });

        // Log the action using admin client
        await logPlatformAdminAction(
          ctx.adminDb,
          ctx.platformAdmin.id,
          "CREATE_ORGANIZATION",
          "organization",
          org.id,
          {
            name: input.name,
            ownerEmail: input.ownerEmail,
            posName: input.posName,
            plan: input.plan,
          },
          ctx.clientIp
        );

        return { organization: org, user };
      }),
  }),

  // ============================================================================
  // Signup Request Management
  // ============================================================================
  signupRequests: router({
    /**
     * List signup requests with filters
     */
    list: platformAdminProcedure
      .input(
        z.object({
          status: z.enum(["PENDING", "APPROVED", "REJECTED"]).optional(),
          limit: z.number().min(1).max(100).default(50),
          offset: z.number().min(0).default(0),
        })
      )
      .query(async ({ ctx, input }) => {
        let query = ctx.db
          .from("organization_signup_requests")
          .select("*", { count: "exact" })
          .order("created_at", { ascending: false })
          .range(input.offset, input.offset + input.limit - 1);

        if (input.status) {
          query = query.eq("status", input.status);
        }

        const { data, error, count } = await query;

        if (error) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: "Failed to fetch signup requests",
          });
        }

        return {
          requests: data ?? [],
          total: count ?? 0,
        };
      }),

    /**
     * Approve a signup request - creates the organization and user
     */
    approve: platformAdminProcedure
      .input(z.object({ id: z.string() }))
      .mutation(async ({ ctx, input }) => {
        // Get the request using admin client (bypasses RLS)
        const { data: request, error: fetchError } = await ctx.adminDb
          .from("organization_signup_requests")
          .select("*")
          .eq("id", input.id)
          .eq("status", "PENDING")
          .single();

        if (fetchError || !request) {
          throw new TRPCError({
            code: "NOT_FOUND",
            message: "Signup request not found or already processed",
          });
        }

        // Create Supabase auth user with a temporary password.
        // The stored password_hash can't be used directly (it would be double-hashed).
        // Instead, create with a temp password and send a recovery link.
        const tempPassword = crypto.randomUUID();
        const { data: authData, error: authError } =
          await ctx.adminDb.auth.admin.createUser({
            email: request.email,
            password: tempPassword,
            email_confirm: true,
          });

        if (authError || !authData.user) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: `Failed to create auth user: ${authError?.message ?? "Unknown error"}`,
          });
        }

        // Send password reset email so user can set their own password
        const { error: recoveryError } =
          await ctx.adminDb.auth.admin.generateLink({
            type: "recovery",
            email: request.email,
          });

        if (recoveryError) {
          // Non-fatal: user was created, they can use "forgot password" flow
          console.warn(`Failed to send recovery email to ${request.email}: ${recoveryError.message}`);
        }

        // Create organization using admin client
        const { data: org, error: orgError } = await ctx.adminDb
          .from("organizations")
          .insert({
            name: request.organization_name,
            slug: request.organization_slug,
            status: "ACTIVE",
          })
          .select()
          .single();

        if (orgError || !org) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: "Failed to create organization",
          });
        }

        // Create user profile using admin client
        const { data: user, error: userError } = await ctx.adminDb
          .from("users")
          .insert({
            auth_id: authData.user.id,
            email: request.email,
            name: request.name,
            organization_id: org.id,
            role: "OWNER",
          })
          .select()
          .single();

        if (userError || !user) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: "Failed to create user profile",
          });
        }

        // Create default location using admin client
        const { data: location } = await ctx.adminDb
          .from("locations")
          .insert({
            name: "Main Location",
            organization_id: org.id,
          })
          .select()
          .single();

        // Create employee record using admin client
        if (location) {
          await ctx.adminDb.from("employees").insert({
            user_id: user.id,
            location_id: location.id,
          });
        }

        // Create default settings using admin client
        await ctx.adminDb.from("organization_settings").insert({
          organization_id: org.id,
          currency: "USD",
          timezone: "America/New_York",
          tax_rate: 0,
          tax_inclusive: false,
        });

        // Update request status using admin client
        await ctx.adminDb
          .from("organization_signup_requests")
          .update({
            status: "APPROVED",
            reviewed_at: new Date().toISOString(),
            reviewed_by: ctx.platformAdmin.id,
          })
          .eq("id", input.id);

        // Log the action using admin client
        await logPlatformAdminAction(
          ctx.adminDb,
          ctx.platformAdmin.id,
          "APPROVE_SIGNUP",
          "signup_request",
          input.id,
          {
            email: request.email,
            organizationName: request.organization_name,
            organizationId: org.id,
          },
          ctx.clientIp
        );

        return { organization: org, user };
      }),

    /**
     * Reject a signup request
     */
    reject: platformAdminProcedure
      .input(
        z.object({
          id: z.string(),
          reason: z.string().min(10, "Reason must be at least 10 characters"),
        })
      )
      .mutation(async ({ ctx, input }) => {
        const { data: request, error } = await ctx.db
          .from("organization_signup_requests")
          .update({
            status: "REJECTED",
            rejection_reason: input.reason,
            reviewed_at: new Date().toISOString(),
            reviewed_by: ctx.platformAdmin.id,
          })
          .eq("id", input.id)
          .eq("status", "PENDING")
          .select()
          .single();

        if (error || !request) {
          throw new TRPCError({
            code: "NOT_FOUND",
            message: "Signup request not found or already processed",
          });
        }

        // Log the action
        await logPlatformAdminAction(
          ctx.db,
          ctx.platformAdmin.id,
          "REJECT_SIGNUP",
          "signup_request",
          input.id,
          { email: request.email, reason: input.reason },
          ctx.clientIp
        );

        return request;
      }),
  }),

  // ============================================================================
  // Impersonation
  // ============================================================================
  impersonation: router({
    /**
     * Start impersonating a user
     */
    start: platformAdminProcedure
      .input(
        z.object({
          userId: z.string(),
          reason: z.string().min(10, "Reason must be at least 10 characters"),
        })
      )
      .mutation(async ({ ctx, input }) => {
        // Get the user to impersonate
        const { data: user, error: userError } = await ctx.db
          .from("users")
          .select("*, organization:organizations(*)")
          .eq("id", input.userId)
          .single();

        if (userError || !user) {
          throw new TRPCError({
            code: "NOT_FOUND",
            message: "User not found",
          });
        }

        // End any existing active sessions for this admin
        await ctx.db
          .from("impersonation_sessions")
          .update({
            is_active: false,
            ended_at: new Date().toISOString(),
          })
          .eq("admin_id", ctx.platformAdmin.id)
          .eq("is_active", true);

        // Create new impersonation session
        const { data: session, error: sessionError } = await ctx.db
          .from("impersonation_sessions")
          .insert({
            admin_id: ctx.platformAdmin.id,
            user_id: input.userId,
            organization_id: user.organization_id,
            reason: input.reason,
          })
          .select()
          .single();

        if (sessionError || !session) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: "Failed to start impersonation session",
          });
        }

        // Log the action
        await logPlatformAdminAction(
          ctx.db,
          ctx.platformAdmin.id,
          "IMPERSONATE_START",
          "user",
          input.userId,
          {
            reason: input.reason,
            sessionId: session.id,
            userName: user.name,
            userEmail: user.email,
          },
          ctx.clientIp
        );

        return {
          session,
          user: {
            id: user.id,
            name: user.name,
            email: user.email,
            role: user.role,
            organizationId: user.organization_id,
          },
        };
      }),

    /**
     * End current impersonation session
     */
    end: platformAdminProcedure.mutation(async ({ ctx }) => {
      const { data: session, error } = await ctx.db
        .from("impersonation_sessions")
        .update({
          is_active: false,
          ended_at: new Date().toISOString(),
        })
        .eq("admin_id", ctx.platformAdmin.id)
        .eq("is_active", true)
        .select()
        .single();

      if (error || !session) {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "No active impersonation session found",
        });
      }

      // Log the action
      await logPlatformAdminAction(
        ctx.db,
        ctx.platformAdmin.id,
        "IMPERSONATE_END",
        "impersonation_session",
        session.id,
        { userId: session.user_id },
        ctx.clientIp
      );

      return { success: true };
    }),

    /**
     * Get current impersonation session
     */
    getCurrent: platformAdminProcedure.query(async ({ ctx }) => {
      const { data: session } = await ctx.db
        .from("impersonation_sessions")
        .select(
          `
          *,
          user:users(id, name, email, role),
          organization:organizations(id, name)
        `
        )
        .eq("admin_id", ctx.platformAdmin.id)
        .eq("is_active", true)
        .single();

      return session;
    }),

    /**
     * List all active impersonation sessions (for monitoring)
     */
    listActive: platformAdminProcedure.query(async ({ ctx }) => {
      const { data: sessions } = await ctx.db
        .from("impersonation_sessions")
        .select(
          `
          *,
          admin:platform_admins(id, name, email),
          user:users(id, name, email, role),
          organization:organizations(id, name)
        `
        )
        .eq("is_active", true)
        .order("started_at", { ascending: false });

      return sessions ?? [];
    }),
  }),

  // ============================================================================
  // Audit Logs
  // ============================================================================
  auditLogs: router({
    /**
     * List audit logs with filters
     */
    list: platformAdminProcedure
      .input(
        z.object({
          action: z.string().optional(),
          adminId: z.string().optional(),
          targetType: z.string().optional(),
          limit: z.number().min(1).max(200).default(100),
          offset: z.number().min(0).default(0),
        })
      )
      .query(async ({ ctx, input }) => {
        let query = ctx.db
          .from("platform_audit_logs")
          .select(
            `
            *,
            admin:platform_admins(id, name, email)
          `,
            { count: "exact" }
          )
          .order("created_at", { ascending: false })
          .range(input.offset, input.offset + input.limit - 1);

        if (input.action) {
          query = query.eq("action", input.action);
        }
        if (input.adminId) {
          query = query.eq("admin_id", input.adminId);
        }
        if (input.targetType) {
          query = query.eq("target_type", input.targetType);
        }

        const { data, error, count } = await query;

        if (error) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: "Failed to fetch audit logs",
          });
        }

        return {
          logs: data ?? [],
          total: count ?? 0,
        };
      }),
  }),

  // ============================================================================
  // Partner Management
  // ============================================================================
  partners: router({
    /**
     * List all partners with optional filters
     */
    list: platformAdminProcedure
      .input(
        z.object({
          status: z.enum(["PENDING", "ACTIVE", "SUSPENDED"]).optional(),
          search: z.string().optional(),
          limit: z.number().min(1).max(100).default(50),
          offset: z.number().min(0).default(0),
        })
      )
      .query(async ({ ctx, input }) => {
        let query = ctx.adminDb
          .from("partners")
          .select(
            `
            *,
            partner_users:partner_users(count),
            partner_organizations:partner_organizations(count)
          `,
            { count: "exact" }
          )
          .order("created_at", { ascending: false })
          .range(input.offset, input.offset + input.limit - 1);

        if (input.status) {
          query = query.eq("status", input.status);
        }

        if (input.search) {
          query = query.or(
            `name.ilike.%${input.search}%,slug.ilike.%${input.search}%,contact_email.ilike.%${input.search}%`
          );
        }

        const { data, error, count } = await query;

        if (error) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: "Failed to fetch partners",
          });
        }

        return {
          partners: data ?? [],
          total: count ?? 0,
        };
      }),

    /**
     * Get partner by ID with full details
     */
    getById: platformAdminProcedure
      .input(z.object({ id: z.string() }))
      .query(async ({ ctx, input }) => {
        const { data: partner, error } = await ctx.adminDb
          .from("partners")
          .select(
            `
            *,
            partner_users:partner_users(id, name, email, role, is_active, created_at),
            partner_organizations:partner_organizations(
              id,
              status,
              billing_plan,
              monthly_fee,
              created_at,
              organization:organizations(id, name, slug, status)
            )
          `
          )
          .eq("id", input.id)
          .single();

        if (error || !partner) {
          throw new TRPCError({
            code: "NOT_FOUND",
            message: "Partner not found",
          });
        }

        return partner;
      }),

    /**
     * Create a new partner
     */
    create: platformAdminProcedure
      .input(
        z.object({
          name: z.string().min(2),
          slug: z.string().min(2).regex(/^[a-z0-9-]+$/, "Slug must be lowercase alphanumeric with hyphens"),
          contactEmail: z.string().email(),
          billingEmail: z.string().email().optional(),
          logo: z.string().url().optional(),
          defaultPosName: z.string().optional(),
          defaultPosLogo: z.string().url().optional(),
          primaryColor: z.string().optional(),
          secondaryColor: z.string().optional(),
          commissionRate: z.number().min(0).max(100).default(10),
          maxOrganizations: z.number().min(1).default(100),
        })
      )
      .mutation(async ({ ctx, input }) => {
        // Check if slug is unique
        const { data: existing } = await ctx.adminDb
          .from("partners")
          .select("id")
          .eq("slug", input.slug)
          .single();

        if (existing) {
          throw new TRPCError({
            code: "CONFLICT",
            message: "A partner with this slug already exists",
          });
        }

        const { data: partner, error } = await ctx.adminDb
          .from("partners")
          .insert({
            name: input.name,
            slug: input.slug,
            contact_email: input.contactEmail,
            billing_email: input.billingEmail || input.contactEmail,
            logo: input.logo,
            default_pos_name: input.defaultPosName,
            default_pos_logo: input.defaultPosLogo,
            primary_color: input.primaryColor,
            secondary_color: input.secondaryColor,
            commission_rate: input.commissionRate,
            max_organizations: input.maxOrganizations,
            status: "ACTIVE",
          })
          .select()
          .single();

        if (error) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: "Failed to create partner",
          });
        }

        // Log the action
        await logPlatformAdminAction(
          ctx.adminDb,
          ctx.platformAdmin.id,
          "CREATE_PARTNER",
          "partner",
          partner.id,
          { name: input.name, slug: input.slug },
          ctx.clientIp
        );

        return partner;
      }),

    /**
     * Update a partner
     */
    update: platformAdminProcedure
      .input(
        z.object({
          id: z.string(),
          name: z.string().min(2).optional(),
          contactEmail: z.string().email().optional(),
          billingEmail: z.string().email().optional(),
          logo: z.string().url().nullable().optional(),
          defaultPosName: z.string().nullable().optional(),
          defaultPosLogo: z.string().url().nullable().optional(),
          primaryColor: z.string().nullable().optional(),
          secondaryColor: z.string().nullable().optional(),
          commissionRate: z.number().min(0).max(100).optional(),
          maxOrganizations: z.number().min(1).optional(),
        })
      )
      .mutation(async ({ ctx, input }) => {
        const { id, ...updates } = input;

        // Convert camelCase to snake_case for database
        const dbUpdates: Record<string, unknown> = {};
        if (updates.name !== undefined) dbUpdates.name = updates.name;
        if (updates.contactEmail !== undefined) dbUpdates.contact_email = updates.contactEmail;
        if (updates.billingEmail !== undefined) dbUpdates.billing_email = updates.billingEmail;
        if (updates.logo !== undefined) dbUpdates.logo = updates.logo;
        if (updates.defaultPosName !== undefined) dbUpdates.default_pos_name = updates.defaultPosName;
        if (updates.defaultPosLogo !== undefined) dbUpdates.default_pos_logo = updates.defaultPosLogo;
        if (updates.primaryColor !== undefined) dbUpdates.primary_color = updates.primaryColor;
        if (updates.secondaryColor !== undefined) dbUpdates.secondary_color = updates.secondaryColor;
        if (updates.commissionRate !== undefined) dbUpdates.commission_rate = updates.commissionRate;
        if (updates.maxOrganizations !== undefined) dbUpdates.max_organizations = updates.maxOrganizations;

        const { data: partner, error } = await ctx.adminDb
          .from("partners")
          .update(dbUpdates)
          .eq("id", id)
          .select()
          .single();

        if (error) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: "Failed to update partner",
          });
        }

        // Log the action
        await logPlatformAdminAction(
          ctx.adminDb,
          ctx.platformAdmin.id,
          "UPDATE_PARTNER",
          "partner",
          id,
          updates,
          ctx.clientIp
        );

        return partner;
      }),

    /**
     * Suspend a partner
     */
    suspend: platformAdminProcedure
      .input(
        z.object({
          id: z.string(),
          reason: z.string().min(10, "Reason must be at least 10 characters"),
        })
      )
      .mutation(async ({ ctx, input }) => {
        const { data: partner, error } = await ctx.adminDb
          .from("partners")
          .update({
            status: "SUSPENDED",
            suspended_at: new Date().toISOString(),
            suspended_reason: input.reason,
          })
          .eq("id", input.id)
          .select()
          .single();

        if (error) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: "Failed to suspend partner",
          });
        }

        // Log the action
        await logPlatformAdminAction(
          ctx.adminDb,
          ctx.platformAdmin.id,
          "SUSPEND_PARTNER",
          "partner",
          input.id,
          { reason: input.reason },
          ctx.clientIp
        );

        return partner;
      }),

    /**
     * Activate a partner
     */
    activate: platformAdminProcedure
      .input(z.object({ id: z.string() }))
      .mutation(async ({ ctx, input }) => {
        const { data: partner, error } = await ctx.adminDb
          .from("partners")
          .update({
            status: "ACTIVE",
            suspended_at: null,
            suspended_reason: null,
          })
          .eq("id", input.id)
          .select()
          .single();

        if (error) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: "Failed to activate partner",
          });
        }

        // Log the action
        await logPlatformAdminAction(
          ctx.adminDb,
          ctx.platformAdmin.id,
          "ACTIVATE_PARTNER",
          "partner",
          input.id,
          {},
          ctx.clientIp
        );

        return partner;
      }),

    /**
     * Create a partner user (for initial setup)
     */
    createUser: platformAdminProcedure
      .input(
        z.object({
          partnerId: z.string(),
          email: z.string().email(),
          name: z.string().min(2),
          password: z.string().min(8),
          role: z.enum(["OWNER", "ADMIN", "BILLING", "SUPPORT", "VIEWER"]),
        })
      )
      .mutation(async ({ ctx, input }) => {
        // Verify partner exists
        const { data: partner, error: partnerError } = await ctx.adminDb
          .from("partners")
          .select("id, name")
          .eq("id", input.partnerId)
          .single();

        if (partnerError || !partner) {
          throw new TRPCError({
            code: "NOT_FOUND",
            message: "Partner not found",
          });
        }

        // Check if user already exists
        const { data: existingUser } = await ctx.adminDb
          .from("partner_users")
          .select("id")
          .eq("email", input.email)
          .single();

        if (existingUser) {
          throw new TRPCError({
            code: "CONFLICT",
            message: "A user with this email already exists",
          });
        }

        // Create Supabase auth user
        const { data: authData, error: authError } =
          await ctx.adminDb.auth.admin.createUser({
            email: input.email,
            password: input.password,
            email_confirm: true,
          });

        if (authError || !authData.user) {
          throw new TRPCError({
            code: "BAD_REQUEST",
            message: authError?.message ?? "Failed to create user",
          });
        }

        // Create partner user record
        const { data: partnerUser, error: userError } = await ctx.adminDb
          .from("partner_users")
          .insert({
            partner_id: input.partnerId,
            auth_id: authData.user.id,
            email: input.email,
            name: input.name,
            role: input.role,
            is_active: true,
          })
          .select()
          .single();

        if (userError) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: "Failed to create partner user",
          });
        }

        // Log the action
        await logPlatformAdminAction(
          ctx.adminDb,
          ctx.platformAdmin.id,
          "CREATE_PARTNER_USER",
          "partner_user",
          partnerUser.id,
          {
            partnerId: input.partnerId,
            partnerName: partner.name,
            email: input.email,
            role: input.role,
          },
          ctx.clientIp
        );

        return partnerUser;
      }),

    /**
     * Delete a partner user
     */
    deleteUser: platformAdminProcedure
      .input(z.object({ userId: z.string() }))
      .mutation(async ({ ctx, input }) => {
        // Get user details before deletion
        const { data: user } = await ctx.adminDb
          .from("partner_users")
          .select("email, name, auth_id, partner_id")
          .eq("id", input.userId)
          .single();

        if (!user) {
          throw new TRPCError({
            code: "NOT_FOUND",
            message: "Partner user not found",
          });
        }

        // Delete partner user record
        const { error: deleteError } = await ctx.adminDb
          .from("partner_users")
          .delete()
          .eq("id", input.userId);

        if (deleteError) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: "Failed to delete partner user",
          });
        }

        // Delete auth user if exists
        if (user.auth_id) {
          await ctx.adminDb.auth.admin.deleteUser(user.auth_id);
        }

        // Log the action
        await logPlatformAdminAction(
          ctx.adminDb,
          ctx.platformAdmin.id,
          "DELETE_PARTNER_USER",
          "partner_user",
          input.userId,
          { email: user.email, name: user.name, partnerId: user.partner_id },
          ctx.clientIp
        );

        return { success: true };
      }),
  }),

  // ============================================================================
  // Platform Stats
  // ============================================================================
  stats: platformAdminProcedure.query(async ({ ctx }) => {
    // Use adminDb to bypass RLS and get accurate counts
    // Get organization counts
    const { count: totalOrgs } = await ctx.adminDb
      .from("organizations")
      .select("*", { count: "exact", head: true });

    const { count: activeOrgs } = await ctx.adminDb
      .from("organizations")
      .select("*", { count: "exact", head: true })
      .eq("status", "ACTIVE");

    const { count: suspendedOrgs } = await ctx.adminDb
      .from("organizations")
      .select("*", { count: "exact", head: true })
      .eq("status", "SUSPENDED");

    // Get pending signup requests
    const { count: pendingSignups } = await ctx.adminDb
      .from("organization_signup_requests")
      .select("*", { count: "exact", head: true })
      .eq("status", "PENDING");

    // Get total users
    const { count: totalUsers } = await ctx.adminDb
      .from("users")
      .select("*", { count: "exact", head: true });

    // Get recent orders count (last 7 days)
    const sevenDaysAgo = new Date();
    sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

    const { count: recentOrders } = await ctx.adminDb
      .from("orders")
      .select("*", { count: "exact", head: true })
      .gte("created_at", sevenDaysAgo.toISOString());

    // Get partner counts
    const { count: totalPartners } = await ctx.adminDb
      .from("partners")
      .select("*", { count: "exact", head: true });

    const { count: activePartners } = await ctx.adminDb
      .from("partners")
      .select("*", { count: "exact", head: true })
      .eq("status", "ACTIVE");

    return {
      organizations: {
        total: totalOrgs ?? 0,
        active: activeOrgs ?? 0,
        suspended: suspendedOrgs ?? 0,
      },
      partners: {
        total: totalPartners ?? 0,
        active: activePartners ?? 0,
      },
      pendingSignups: pendingSignups ?? 0,
      totalUsers: totalUsers ?? 0,
      recentOrders: recentOrders ?? 0,
    };
  }),
});

export type PlatformAdminRouter = typeof platformAdminRouter;
