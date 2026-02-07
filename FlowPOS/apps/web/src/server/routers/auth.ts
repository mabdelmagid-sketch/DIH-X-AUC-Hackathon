import { z } from "zod";
import { router, publicProcedure, protectedProcedure } from "../trpc";
import { TRPCError } from "@trpc/server";
import bcrypt from "bcryptjs";
import { logger } from "@/lib/logger";
import { createAdminDb } from "../db";

// Rate limiting for PIN verification (brute-force protection)
const PIN_RATE_LIMIT = {
  maxAttempts: 5,           // Max attempts per window
  windowMs: 15 * 60 * 1000, // 15 minute window
  lockoutMs: 30 * 60 * 1000, // 30 minute lockout after max attempts
};

// In-memory store for rate limiting (use Redis in production for multi-instance)
const pinAttempts = new Map<string, { count: number; firstAttempt: number; lockedUntil?: number }>();

function checkPinRateLimit(ip: string): { allowed: boolean; retryAfter?: number } {
  const now = Date.now();
  const record = pinAttempts.get(ip);

  if (!record) {
    return { allowed: true };
  }

  // Check if currently locked out
  if (record.lockedUntil && now < record.lockedUntil) {
    return { allowed: false, retryAfter: Math.ceil((record.lockedUntil - now) / 1000) };
  }

  // Check if window has expired, reset if so
  if (now - record.firstAttempt > PIN_RATE_LIMIT.windowMs) {
    pinAttempts.delete(ip);
    return { allowed: true };
  }

  // Check if max attempts exceeded
  if (record.count >= PIN_RATE_LIMIT.maxAttempts) {
    record.lockedUntil = now + PIN_RATE_LIMIT.lockoutMs;
    return { allowed: false, retryAfter: Math.ceil(PIN_RATE_LIMIT.lockoutMs / 1000) };
  }

  return { allowed: true };
}

function recordPinAttempt(ip: string, success: boolean): void {
  if (success) {
    pinAttempts.delete(ip);
    return;
  }

  const now = Date.now();
  const record = pinAttempts.get(ip);

  if (!record || now - record.firstAttempt > PIN_RATE_LIMIT.windowMs) {
    pinAttempts.set(ip, { count: 1, firstAttempt: now });
  } else {
    record.count++;
  }
}

// Clean up expired entries periodically (every 5 minutes)
setInterval(() => {
  const now = Date.now();
  for (const [ip, record] of pinAttempts.entries()) {
    if (now - record.firstAttempt > PIN_RATE_LIMIT.windowMs && (!record.lockedUntil || now > record.lockedUntil)) {
      pinAttempts.delete(ip);
    }
  }
}, 5 * 60 * 1000);

// PIN hashing utilities
const BCRYPT_ROUNDS = 10;

async function hashPin(pin: string): Promise<string> {
  return bcrypt.hash(pin, BCRYPT_ROUNDS);
}

async function verifyPinHash(pin: string, hashedPin: string): Promise<boolean> {
  // All PINs should be bcrypt hashed after migration 20260206_hash_existing_plaintext_pins
  if (hashedPin.startsWith("$2")) {
    return bcrypt.compare(pin, hashedPin);
  }
  // No plaintext fallback - PINs must be hashed
  return false;
}

function isPinHashed(pin: string): boolean {
  return pin.startsWith("$2");
}

// Zod schemas for validation
const signUpSchema = z.object({
  email: z.string().email("Invalid email address"),
  password: z
    .string()
    .min(8, "Password must be at least 8 characters")
    .regex(/[A-Z]/, "Password must contain at least one uppercase letter")
    .regex(/[a-z]/, "Password must contain at least one lowercase letter")
    .regex(/[0-9]/, "Password must contain at least one number"),
  name: z.string().min(2, "Name must be at least 2 characters").max(100),
  organizationName: z
    .string()
    .min(2, "Business name must be at least 2 characters")
    .max(100),
});

const signInSchema = z.object({
  email: z.string().email("Invalid email address"),
  password: z.string().min(1, "Password is required"),
});

const magicLinkSchema = z.object({
  email: z.string().email("Invalid email address"),
});

const resetPasswordSchema = z.object({
  email: z.string().email("Invalid email address"),
});

const updatePasswordSchema = z.object({
  password: z
    .string()
    .min(8, "Password must be at least 8 characters")
    .regex(/[A-Z]/, "Password must contain at least one uppercase letter")
    .regex(/[a-z]/, "Password must contain at least one lowercase letter")
    .regex(/[0-9]/, "Password must contain at least one number"),
});

const verifyPinSchema = z.object({
  pin: z.string().regex(/^\d{4,6}$/, "PIN must be 4-6 digits"),
});

// Store-scoped PIN verification schema
const verifyStorePinSchema = z.object({
  storeCode: z.string().min(1, "Store code is required"),
  pin: z.string().regex(/^\d{4,6}$/, "PIN must be 4-6 digits"),
});

const managerOverrideSchema = z.object({
  storeCode: z.string().min(1, "Store code is required"),
  managerPin: z.string().regex(/^\d{4,6}$/, "Manager PIN must be 4-6 digits"),
});

const changePinSchema = z.object({
  currentPin: z.string().regex(/^\d{4,6}$/, "Current PIN must be 4-6 digits"),
  newPin: z.string().regex(/^\d{4,6}$/, "New PIN must be 4-6 digits"),
});

export const authRouter = router({
  // Get current authenticated user
  me: publicProcedure.query(async ({ ctx }) => {
    if (!ctx.user) {
      return null;
    }

    // Get full user data with organization and location
    const { data: userData, error: userError } = await ctx.db
      .from("users")
      .select("*")
      .eq("id", ctx.user.id)
      .single();

    if (userError || !userData) {
      return null;
    }

    // Get organization
    const { data: orgData } = await ctx.db
      .from("organizations")
      .select("*")
      .eq("id", userData.organization_id)
      .single();

    // Get employee data if exists
    const { data: employeeData } = await ctx.db
      .from("employees")
      .select("*, location:locations(*)")
      .eq("user_id", userData.id)
      .single();

    return {
      user: userData,
      organization: orgData,
      employee: employeeData,
      location: employeeData?.location ?? null,
    };
  }),

  // Sign up with email and password
  signUp: publicProcedure.input(signUpSchema).mutation(async ({ ctx, input }) => {
    // 1. Create auth user with Supabase
    const { data: authData, error: authError } = await ctx.db.auth.signUp({
      email: input.email,
      password: input.password,
      options: {
        data: {
          name: input.name,
        },
      },
    });

    if (authError) {
      throw new TRPCError({
        code: "BAD_REQUEST",
        message: authError.message,
      });
    }

    if (!authData.user) {
      throw new TRPCError({
        code: "INTERNAL_SERVER_ERROR",
        message: "Failed to create user",
      });
    }

    // 2. Create organization
    const orgSlug = input.organizationName
      .toLowerCase()
      .replace(/\s+/g, "-")
      .replace(/[^a-z0-9-]/g, "");

    const { data: orgData, error: orgError } = await ctx.db
      .from("organizations")
      .insert({
        name: input.organizationName,
        slug: `${orgSlug}-${Date.now()}`,
      })
      .select()
      .single();

    if (orgError || !orgData) {
      throw new TRPCError({
        code: "INTERNAL_SERVER_ERROR",
        message: "Failed to create organization",
      });
    }

    // 3. Create user profile
    const { data: profileData, error: profileError } = await ctx.db
      .from("users")
      .insert({
        auth_id: authData.user.id,
        email: input.email,
        name: input.name,
        organization_id: orgData.id,
        role: "OWNER",
      })
      .select()
      .single();

    if (profileError) {
      throw new TRPCError({
        code: "INTERNAL_SERVER_ERROR",
        message: "Failed to create user profile",
      });
    }

    // 4. Create default location
    const { data: locationData } = await ctx.db
      .from("locations")
      .insert({
        organization_id: orgData.id,
        name: "Main Location",
      })
      .select()
      .single();

    // 5. Create employee record linked to user
    if (locationData) {
      await ctx.db.from("employees").insert({
        user_id: profileData.id,
        location_id: locationData.id,
      });
    }

    // 6. Create organization settings
    await ctx.db.from("organization_settings").insert({
      organization_id: orgData.id,
    });

    return {
      user: profileData,
      organization: orgData,
      location: locationData,
      requiresEmailConfirmation: !authData.session,
    };
  }),

  /**
   * Request signup with approval
   * Creates a pending signup request that must be approved by platform admin
   */
  requestSignUp: publicProcedure
    .input(signUpSchema)
    .mutation(async ({ ctx, input }) => {
      // Check for existing user with this email
      const { data: existingUser } = await ctx.db
        .from("users")
        .select("id")
        .eq("email", input.email)
        .single();

      if (existingUser) {
        throw new TRPCError({
          code: "CONFLICT",
          message: "An account with this email already exists",
        });
      }

      // Check for existing pending request
      const { data: existingRequest } = await ctx.db
        .from("organization_signup_requests")
        .select("id, status")
        .eq("email", input.email)
        .order("created_at", { ascending: false })
        .limit(1)
        .single();

      if (existingRequest) {
        if (existingRequest.status === "PENDING") {
          throw new TRPCError({
            code: "CONFLICT",
            message:
              "A signup request for this email is already pending approval",
          });
        }
        // If rejected, allow resubmission
      }

      // Generate organization slug
      const slug = `${input.organizationName
        .toLowerCase()
        .replace(/\s+/g, "-")
        .replace(/[^a-z0-9-]/g, "")}-${Date.now()}`;

      // Hash the password for storage
      const hashedPassword = await bcrypt.hash(input.password, BCRYPT_ROUNDS);

      // Create signup request
      const { data: request, error } = await ctx.db
        .from("organization_signup_requests")
        .insert({
          email: input.email,
          name: input.name,
          password_hash: hashedPassword,
          organization_name: input.organizationName,
          organization_slug: slug,
          status: "PENDING",
          ip_address: ctx.clientIp,
        })
        .select()
        .single();

      if (error || !request) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: "Failed to submit signup request",
        });
      }

      return {
        success: true,
        message:
          "Your signup request has been submitted and is pending approval. You will receive an email once your account is approved.",
        requestId: request.id,
      };
    }),

  /**
   * Check signup request status
   */
  checkSignUpStatus: publicProcedure
    .input(z.object({ email: z.string().email() }))
    .query(async ({ ctx, input }) => {
      const { data: request } = await ctx.db
        .from("organization_signup_requests")
        .select("id, status, rejection_reason, created_at, reviewed_at")
        .eq("email", input.email)
        .order("created_at", { ascending: false })
        .limit(1)
        .single();

      if (!request) {
        return { found: false };
      }

      return {
        found: true,
        status: request.status,
        rejectionReason: request.rejection_reason,
        submittedAt: request.created_at,
        reviewedAt: request.reviewed_at,
      };
    }),

  // Sign in with email and password
  signIn: publicProcedure.input(signInSchema).mutation(async ({ ctx, input }) => {
    const { data, error } = await ctx.db.auth.signInWithPassword({
      email: input.email,
      password: input.password,
    });

    if (error) {
      throw new TRPCError({
        code: "UNAUTHORIZED",
        message: "Invalid email or password",
      });
    }

    if (!data.user) {
      throw new TRPCError({
        code: "UNAUTHORIZED",
        message: "Invalid email or password",
      });
    }

    // Fetch user profile
    const { data: profile } = await ctx.db
      .from("users")
      .select("*")
      .eq("auth_id", data.user.id)
      .single();

    if (!profile) {
      throw new TRPCError({
        code: "NOT_FOUND",
        message: "User profile not found",
      });
    }

    return {
      user: profile,
      session: data.session,
    };
  }),

  // Sign out
  signOut: protectedProcedure.mutation(async ({ ctx }) => {
    const { error } = await ctx.db.auth.signOut();

    if (error) {
      throw new TRPCError({
        code: "INTERNAL_SERVER_ERROR",
        message: error.message,
      });
    }

    return { success: true };
  }),

  // Send magic link for passwordless login
  sendMagicLink: publicProcedure
    .input(magicLinkSchema)
    .mutation(async ({ ctx, input }) => {
      // First check if user exists
      const { data: existingUser } = await ctx.db
        .from("users")
        .select("id")
        .eq("email", input.email)
        .single();

      if (!existingUser) {
        // Don't reveal if email exists or not for security
        return { success: true, message: "If an account exists, a magic link has been sent" };
      }

      const { error } = await ctx.db.auth.signInWithOtp({
        email: input.email,
        options: {
          emailRedirectTo: `${process.env.NEXT_PUBLIC_APP_URL}/auth/callback`,
        },
      });

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: "Failed to send magic link",
        });
      }

      return { success: true, message: "Magic link sent to your email" };
    }),

  // Request password reset
  requestPasswordReset: publicProcedure
    .input(resetPasswordSchema)
    .mutation(async ({ ctx, input }) => {
      const { error } = await ctx.db.auth.resetPasswordForEmail(input.email, {
        redirectTo: `${process.env.NEXT_PUBLIC_APP_URL}/auth/reset-password`,
      });

      if (error) {
        // Don't reveal if email exists or not for security
        logger.error("Password reset error", error);
      }

      return {
        success: true,
        message: "If an account exists with this email, a password reset link has been sent",
      };
    }),

  // Update password (after reset or authenticated)
  updatePassword: protectedProcedure
    .input(updatePasswordSchema)
    .mutation(async ({ ctx, input }) => {
      const { error } = await ctx.db.auth.updateUser({
        password: input.password,
      });

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return { success: true };
    }),

  // Verify employee PIN
  verifyPin: publicProcedure.input(verifyPinSchema).mutation(async ({ ctx, input }) => {
    // Check rate limit before processing
    const rateLimitCheck = checkPinRateLimit(ctx.clientIp);
    if (!rateLimitCheck.allowed) {
      throw new TRPCError({
        code: "TOO_MANY_REQUESTS",
        message: `Too many PIN attempts. Please try again in ${Math.ceil((rateLimitCheck.retryAfter ?? 1800) / 60)} minutes.`,
      });
    }

    // Get all active employees with PINs to verify against
    const { data: employees, error } = await ctx.db
      .from("employees")
      .select(
        `
        *,
        user:users(*),
        location:locations(*)
      `
      )
      .eq("is_active", true)
      .not("pin", "is", null);

    if (error || !employees || employees.length === 0) {
      recordPinAttempt(ctx.clientIp, false);
      throw new TRPCError({
        code: "UNAUTHORIZED",
        message: "Invalid PIN",
      });
    }

    // Find the employee with matching PIN (supports both hashed and legacy plain text)
    let matchedEmployee = null;
    for (const emp of employees) {
      if (emp.pin && (await verifyPinHash(input.pin, emp.pin))) {
        matchedEmployee = emp;
        break;
      }
    }

    if (!matchedEmployee) {
      recordPinAttempt(ctx.clientIp, false);
      throw new TRPCError({
        code: "UNAUTHORIZED",
        message: "Invalid PIN",
      });
    }

    // Successful authentication - clear rate limit
    recordPinAttempt(ctx.clientIp, true);

    // Auto-upgrade legacy plain text PIN to hashed version
    if (matchedEmployee.pin && !isPinHashed(matchedEmployee.pin)) {
      const hashedPin = await hashPin(input.pin);
      await ctx.db
        .from("employees")
        .update({ pin: hashedPin })
        .eq("id", matchedEmployee.id);
    }

    const userData = matchedEmployee.user as {
      id: string;
      email: string;
      name: string;
      role: string;
      organization_id: string;
    } | null;

    if (!userData) {
      throw new TRPCError({
        code: "UNAUTHORIZED",
        message: "Invalid PIN",
      });
    }

    // Get organization
    const { data: org } = await ctx.db
      .from("organizations")
      .select("*")
      .eq("id", userData.organization_id)
      .single();

    // Get organization settings
    const { data: orgSettings } = await ctx.db
      .from("organization_settings")
      .select("*")
      .eq("organization_id", userData.organization_id)
      .single();

    return {
      employee: matchedEmployee,
      user: userData,
      organization: org,
      organizationSettings: orgSettings,
      location: matchedEmployee.location,
    };
  }),

  // Change PIN (authenticated employee)
  changePin: protectedProcedure.input(changePinSchema).mutation(async ({ ctx, input }) => {
    // Get current employee
    const { data: employee, error: fetchError } = await ctx.db
      .from("employees")
      .select("id, pin")
      .eq("user_id", ctx.user.id)
      .single();

    if (fetchError || !employee) {
      throw new TRPCError({
        code: "NOT_FOUND",
        message: "Employee record not found",
      });
    }

    // Verify current PIN (supports both hashed and legacy plain text)
    if (!employee.pin || !(await verifyPinHash(input.currentPin, employee.pin))) {
      throw new TRPCError({
        code: "UNAUTHORIZED",
        message: "Current PIN is incorrect",
      });
    }

    // Check if new PIN is already in use - need to check all employees
    const { data: allEmployees } = await ctx.db
      .from("employees")
      .select("id, pin")
      .neq("id", employee.id)
      .not("pin", "is", null);

    if (allEmployees) {
      for (const emp of allEmployees) {
        if (emp.pin && (await verifyPinHash(input.newPin, emp.pin))) {
          throw new TRPCError({
            code: "CONFLICT",
            message: "This PIN is already in use",
          });
        }
      }
    }

    // Hash and update PIN
    const hashedPin = await hashPin(input.newPin);
    const { error: updateError } = await ctx.db
      .from("employees")
      .update({ pin: hashedPin })
      .eq("id", employee.id);

    if (updateError) {
      throw new TRPCError({
        code: "INTERNAL_SERVER_ERROR",
        message: updateError.message,
      });
    }

    return { success: true };
  }),

  // Set PIN (for employees without one)
  setPin: protectedProcedure
    .input(z.object({ pin: z.string().regex(/^\d{4,6}$/, "PIN must be 4-6 digits") }))
    .mutation(async ({ ctx, input }) => {
      // Get current employee
      const { data: employee, error: fetchError } = await ctx.db
        .from("employees")
        .select("id, pin")
        .eq("user_id", ctx.user.id)
        .single();

      if (fetchError || !employee) {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "Employee record not found",
        });
      }

      // Check if new PIN is already in use - need to check all employees
      const { data: allEmployees } = await ctx.db
        .from("employees")
        .select("id, pin")
        .neq("id", employee.id)
        .not("pin", "is", null);

      if (allEmployees) {
        for (const emp of allEmployees) {
          if (emp.pin && (await verifyPinHash(input.pin, emp.pin))) {
            throw new TRPCError({
              code: "CONFLICT",
              message: "This PIN is already in use",
            });
          }
        }
      }

      // Hash and update PIN
      const hashedPin = await hashPin(input.pin);
      const { error: updateError } = await ctx.db
        .from("employees")
        .update({ pin: hashedPin })
        .eq("id", employee.id);

      if (updateError) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: updateError.message,
        });
      }

      return { success: true };
    }),

  // Get store info by code (slug) - for PIN login page
  getStoreByCode: publicProcedure
    .input(z.object({ code: z.string().min(1) }))
    .query(async ({ ctx, input }) => {
      const { data: org, error } = await ctx.db
        .from("organizations")
        .select("id, name, slug, logo, status")
        .eq("slug", input.code)
        .eq("status", "ACTIVE")
        .single();

      if (error || !org) {
        return null;
      }

      return {
        id: org.id,
        name: org.name,
        code: org.slug,
        logo: org.logo,
      };
    }),

  // Verify PIN scoped to a specific store
  verifyStorePin: publicProcedure
    .input(verifyStorePinSchema)
    .mutation(async ({ ctx, input }) => {
      // Check rate limit before processing
      const rateLimitCheck = checkPinRateLimit(ctx.clientIp);
      if (!rateLimitCheck.allowed) {
        throw new TRPCError({
          code: "TOO_MANY_REQUESTS",
          message: `Too many PIN attempts. Please try again in ${Math.ceil((rateLimitCheck.retryAfter ?? 1800) / 60)} minutes.`,
        });
      }

      // Use admin client to bypass RLS for PIN verification
      const adminDb = createAdminDb();

      // 1. Get the organization by slug
      const { data: org, error: orgError } = await adminDb
        .from("organizations")
        .select("id, name, slug, logo, status")
        .eq("slug", input.storeCode)
        .eq("status", "ACTIVE")
        .single();

      if (orgError || !org) {
        recordPinAttempt(ctx.clientIp, false);
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "Store not found or inactive",
        });
      }

      // 2. Get all locations for this organization
      const { data: locations } = await adminDb
        .from("locations")
        .select("id")
        .eq("organization_id", org.id)
        .eq("is_active", true);

      if (!locations || locations.length === 0) {
        recordPinAttempt(ctx.clientIp, false);
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "No active locations for this store",
        });
      }

      const locationIds = locations.map((l) => l.id);

      // 3. Get all active employees for these locations with PINs
      const { data: employees, error: empError } = await adminDb
        .from("employees")
        .select(
          `
          *,
          user:users(*),
          location:locations(*)
        `
        )
        .in("location_id", locationIds)
        .eq("is_active", true)
        .not("pin", "is", null);

      if (empError || !employees || employees.length === 0) {
        recordPinAttempt(ctx.clientIp, false);
        throw new TRPCError({
          code: "UNAUTHORIZED",
          message: "Invalid PIN",
        });
      }

      // 4. Find the employee with matching PIN
      let matchedEmployee = null;
      for (const emp of employees) {
        if (emp.pin && (await verifyPinHash(input.pin, emp.pin))) {
          matchedEmployee = emp;
          break;
        }
      }

      if (!matchedEmployee) {
        recordPinAttempt(ctx.clientIp, false);
        throw new TRPCError({
          code: "UNAUTHORIZED",
          message: "Invalid PIN",
        });
      }

      // Successful authentication - clear rate limit
      recordPinAttempt(ctx.clientIp, true);

      // Auto-upgrade legacy plain text PIN to hashed version
      if (matchedEmployee.pin && !isPinHashed(matchedEmployee.pin)) {
        const hashedPin = await hashPin(input.pin);
        await adminDb
          .from("employees")
          .update({ pin: hashedPin })
          .eq("id", matchedEmployee.id);
      }

      const userData = matchedEmployee.user as {
        id: string;
        email: string;
        name: string;
        role: string;
        organization_id: string;
      } | null;

      if (!userData) {
        throw new TRPCError({
          code: "UNAUTHORIZED",
          message: "Invalid PIN",
        });
      }

      // Get organization settings
      const { data: orgSettings } = await adminDb
        .from("organization_settings")
        .select("*")
        .eq("organization_id", org.id)
        .single();

      return {
        employee: matchedEmployee,
        user: userData,
        organization: {
          id: org.id,
          name: org.name,
          slug: org.slug,
          logo: org.logo,
        },
        organizationSettings: orgSettings,
        location: matchedEmployee.location,
      };
    }),

  // Manager override to unlock a locked terminal
  managerOverride: publicProcedure
    .input(managerOverrideSchema)
    .mutation(async ({ ctx, input }) => {
      // 1. Get the organization by slug
      const { data: org, error: orgError } = await ctx.db
        .from("organizations")
        .select("id, name, slug")
        .eq("slug", input.storeCode)
        .eq("status", "ACTIVE")
        .single();

      if (orgError || !org) {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "Store not found or inactive",
        });
      }

      // 2. Get all locations for this organization
      const { data: locations } = await ctx.db
        .from("locations")
        .select("id")
        .eq("organization_id", org.id)
        .eq("is_active", true);

      if (!locations || locations.length === 0) {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "No active locations for this store",
        });
      }

      const locationIds = locations.map((l) => l.id);

      // 3. Get all active employees with manager/admin/owner role
      const { data: managers, error: empError } = await ctx.db
        .from("employees")
        .select(
          `
          *,
          user:users(*)
        `
        )
        .in("location_id", locationIds)
        .eq("is_active", true)
        .not("pin", "is", null);

      if (empError || !managers || managers.length === 0) {
        throw new TRPCError({
          code: "UNAUTHORIZED",
          message: "Invalid manager PIN",
        });
      }

      // 4. Find a matching manager (must be OWNER, ADMIN, or MANAGER role)
      let matchedManager = null;
      for (const emp of managers) {
        const userData = emp.user as { role?: string } | null;
        if (!userData?.role) continue;

        const isManager = ["OWNER", "ADMIN", "MANAGER"].includes(userData.role);
        if (isManager && emp.pin && (await verifyPinHash(input.managerPin, emp.pin))) {
          matchedManager = emp;
          break;
        }
      }

      if (!matchedManager) {
        throw new TRPCError({
          code: "UNAUTHORIZED",
          message: "Invalid manager PIN. Only managers, admins, or owners can unlock the terminal.",
        });
      }

      // Auto-upgrade legacy plain text PIN to hashed version
      if (matchedManager.pin && !isPinHashed(matchedManager.pin)) {
        const hashedPin = await hashPin(input.managerPin);
        await ctx.db
          .from("employees")
          .update({ pin: hashedPin })
          .eq("id", matchedManager.id);
      }

      // 5. Clear the lockout for this IP
      pinAttempts.delete(ctx.clientIp);

      const userData = matchedManager.user as { name?: string } | null;

      return {
        success: true,
        message: `Terminal unlocked by ${userData?.name ?? "Manager"}`,
      };
    }),

  // Refresh session
  refreshSession: publicProcedure.mutation(async ({ ctx }) => {
    const { data, error } = await ctx.db.auth.refreshSession();

    if (error) {
      throw new TRPCError({
        code: "UNAUTHORIZED",
        message: "Session expired",
      });
    }

    return { session: data.session };
  }),

  // Get session status
  getSession: publicProcedure.query(async ({ ctx }) => {
    const {
      data: { session },
    } = await ctx.db.auth.getSession();

    return {
      isAuthenticated: !!session,
      expiresAt: session?.expires_at,
    };
  }),
});
