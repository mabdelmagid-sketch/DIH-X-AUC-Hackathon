import { z } from "zod";
import {
  router,
  protectedProcedure,
  employeeViewProcedure,
  employeeEditProcedure,
  createPermissionProcedure,
} from "../trpc";
import { TRPCError } from "@trpc/server";

// Special procedures for employee management
const employeeDeleteProcedure = createPermissionProcedure("employees:delete");
const employeeCreateProcedure = createPermissionProcedure("employees:create");

const userRoleSchema = z.enum(["OWNER", "ADMIN", "MANAGER", "STAFF", "KITCHEN"]);

// Employee create schema
const employeeCreateSchema = z.object({
  email: z.string().email("Invalid email"),
  name: z.string().min(1, "Name is required").max(255),
  role: userRoleSchema.default("STAFF"),
  locationId: z.string().min(1),
  pin: z
    .string()
    .regex(/^\d{4,6}$/, "PIN must be 4-6 digits")
    .optional()
    .nullable(),
  hourlyRate: z.number().int().min(0).optional().nullable(),
});

const employeeUpdateSchema = z.object({
  name: z.string().min(1).max(255).optional(),
  role: userRoleSchema.optional(),
  locationId: z.string().min(1).optional(),
  pin: z
    .string()
    .regex(/^\d{4,6}$/, "PIN must be 4-6 digits")
    .optional()
    .nullable(),
  hourlyRate: z.number().int().min(0).optional().nullable(),
  isActive: z.boolean().optional(),
});

const employeeIdSchema = z.object({
  id: z.string().min(1),
});

export const employeesRouter = router({
  // Get all employees for the organization
  list: employeeViewProcedure
    .input(
      z
        .object({
          locationId: z.string().min(1).optional(),
          isActive: z.boolean().optional(),
          role: userRoleSchema.optional(),
        })
        .optional()
    )
    .query(async ({ ctx, input }) => {
      // First get all users in the organization
      let usersQuery = ctx.db
        .from("users")
        .select("*")
        .eq("organization_id", ctx.organizationId);

      if (input?.role) {
        usersQuery = usersQuery.eq("role", input.role);
      }

      const { data: users, error: usersError } = await usersQuery;

      if (usersError) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: usersError.message,
        });
      }

      // Get employees with their user data (excludes soft-deleted)
      let query = ctx.db
        .from("employees")
        .select("*, user:users(*)")
        .is("deleted_at", null); // Exclude soft-deleted employees

      if (input?.locationId) {
        query = query.eq("location_id", input.locationId);
      }

      if (input?.isActive !== undefined) {
        query = query.eq("is_active", input.isActive);
      }

      const { data: employees, error } = await query;

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      // Filter to only include employees belonging to org users
      const userIds = new Set((users ?? []).map((u) => u.id));
      const filteredEmployees = (employees ?? []).filter((e) =>
        userIds.has(e.user_id)
      );

      return filteredEmployees;
    }),

  // Get single employee by ID
  getById: employeeViewProcedure
    .input(employeeIdSchema)
    .query(async ({ ctx, input }) => {
      const { data, error } = await ctx.db
        .from("employees")
        .select("*, user:users(*), location:locations(*)")
        .eq("id", input.id)
        .single();

      if (error) {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "Employee not found",
        });
      }

      // Verify employee belongs to organization
      const user = data.user as { organization_id: string } | null;
      if (user?.organization_id !== ctx.organizationId) {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "Employee not found",
        });
      }

      return data;
    }),

  // Get current employee (for the logged-in user)
  getCurrent: protectedProcedure.query(async ({ ctx }) => {
    const { data, error } = await ctx.db
      .from("employees")
      .select("*, user:users(*), location:locations(*)")
      .eq("user_id", ctx.user.id)
      .single();

    if (error) {
      return null;
    }

    return data;
  }),

  // Verify PIN (for quick login) - kept as protectedProcedure since any authenticated user can verify
  // SECURITY FIX: Filter by organization in the query to prevent cross-org PIN enumeration
  verifyPin: protectedProcedure
    .input(z.object({ pin: z.string() }))
    .mutation(async ({ ctx, input }) => {
      // Use inner join with users table to filter by organization at query level
      // This prevents cross-organization PIN enumeration attacks
      const { data: employee, error } = await ctx.db
        .from("employees")
        .select("*, user:users!inner(*)")
        .eq("pin", input.pin)
        .eq("is_active", true)
        .eq("user.organization_id", ctx.organizationId)
        .single();

      if (error || !employee) {
        throw new TRPCError({
          code: "UNAUTHORIZED",
          message: "Invalid PIN",
        });
      }

      return {
        employee,
        user: employee.user,
      };
    }),

  // Create new employee (creates both user and employee record)
  create: employeeCreateProcedure
    .input(employeeCreateSchema)
    .mutation(async ({ ctx, input }) => {
      // Check if user with email already exists
      const { data: existingUser } = await ctx.db
        .from("users")
        .select("id")
        .eq("email", input.email)
        .single();

      if (existingUser) {
        throw new TRPCError({
          code: "CONFLICT",
          message: "A user with this email already exists",
        });
      }

      // Create user first
      const { data: user, error: userError } = await ctx.db
        .from("users")
        .insert({
          organization_id: ctx.organizationId,
          email: input.email,
          name: input.name,
          role: input.role,
        })
        .select()
        .single();

      if (userError) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: userError.message,
        });
      }

      // Create employee record
      const { data: employee, error: employeeError } = await ctx.db
        .from("employees")
        .insert({
          user_id: user.id,
          location_id: input.locationId,
          pin: input.pin,
          hourly_rate: input.hourlyRate,
        })
        .select()
        .single();

      if (employeeError) {
        // Rollback user creation
        await ctx.db.from("users").delete().eq("id", user.id);
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: employeeError.message,
        });
      }

      return { user, employee };
    }),

  // Update employee (atomic - updates both employees and users tables in a single transaction)
  update: employeeEditProcedure
    .input(employeeIdSchema.merge(employeeUpdateSchema))
    .mutation(async ({ ctx, input }) => {
      const { id, ...updateData } = input;

      const { data, error } = await (ctx.db.rpc as CallableFunction)(
        "update_employee_atomic",
        {
          p_employee_id: id,
          p_name: updateData.name ?? null,
          p_role: updateData.role ?? null,
          p_location_id: updateData.locationId ?? null,
          p_pin: updateData.pin ?? null,
          p_hourly_rate: updateData.hourlyRate ?? null,
          p_is_active: updateData.isActive ?? null,
          p_organization_id: ctx.organizationId,
        }
      );

      if (error) {
        if (error.code === "P0002") {
          throw new TRPCError({
            code: "NOT_FOUND",
            message: "Employee not found",
          });
        }
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      // Fetch updated employee with relations
      const { data: updatedEmployee, error: fetchError } = await ctx.db
        .from("employees")
        .select("*, user:users(*)")
        .eq("id", id)
        .single();

      if (fetchError) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: fetchError.message,
        });
      }

      return updatedEmployee;
    }),

  // Deactivate employee
  deactivate: employeeEditProcedure.input(employeeIdSchema).mutation(async ({ ctx, input }) => {
    const { data, error } = await ctx.db
      .from("employees")
      .update({ is_active: false })
      .eq("id", input.id)
      .select("*, user:users(*)")
      .single();

    if (error) {
      throw new TRPCError({
        code: "INTERNAL_SERVER_ERROR",
        message: error.message,
      });
    }

    return data;
  }),

  // Reactivate employee
  reactivate: employeeEditProcedure.input(employeeIdSchema).mutation(async ({ ctx, input }) => {
    const { data, error } = await ctx.db
      .from("employees")
      .update({ is_active: true })
      .eq("id", input.id)
      .select("*, user:users(*)")
      .single();

    if (error) {
      throw new TRPCError({
        code: "INTERNAL_SERVER_ERROR",
        message: error.message,
      });
    }

    return data;
  }),

  // Soft delete employee (atomic - deactivates employee and user in a single transaction)
  delete: employeeDeleteProcedure.input(employeeIdSchema).mutation(async ({ ctx, input }) => {
    const { error } = await (ctx.db.rpc as CallableFunction)(
      "delete_employee_atomic",
      {
        p_employee_id: input.id,
        p_organization_id: ctx.organizationId,
      }
    );

    if (error) {
      if (error.code === "P0002") {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "Employee not found",
        });
      }
      throw new TRPCError({
        code: "INTERNAL_SERVER_ERROR",
        message: error.message,
      });
    }

    return { success: true };
  }),

  // Note: Time clock functionality (clockIn, clockOut, getClockStatus, getTimeClockHistory)
  // will be added once the time_clocks table is created in Supabase
});
