import { z } from "zod";
import {
  router,
  customerViewProcedure,
  customerEditProcedure,
} from "../trpc";
import { TRPCError } from "@trpc/server";

const customerCreateSchema = z.object({
  name: z.string().min(1, "Name is required").max(255),
  email: z.string().email().max(255).optional().nullable(),
  phone: z.string().max(50).optional().nullable(),
  notes: z.string().max(2000).optional().nullable(),
});

const customerUpdateSchema = customerCreateSchema.partial();

const customerIdSchema = z.object({
  id: z.string(),
});

const listQuerySchema = z.object({
  search: z.string().optional(),
  limit: z.number().int().min(1).max(100).default(50),
  offset: z.number().int().min(0).default(0),
  sortBy: z.enum(["name", "total_spent", "visit_count", "created_at"]).default("name"),
  sortDir: z.enum(["asc", "desc"]).default("asc"),
});

export const customersRouter = router({
  // List customers for the organization
  list: customerViewProcedure
    .input(listQuerySchema.optional())
    .query(async ({ ctx, input }) => {
      const sortBy = input?.sortBy ?? "name";
      const ascending = (input?.sortDir ?? "asc") === "asc";

      let query = ctx.db
        .from("customers")
        .select("*", { count: "exact" })
        .eq("organization_id", ctx.organizationId)
        .is("deleted_at", null)
        .order(sortBy, { ascending });

      if (input?.search) {
        query = query.or(
          `name.ilike.%${input.search}%,email.ilike.%${input.search}%,phone.ilike.%${input.search}%`
        );
      }

      query = query.range(
        input?.offset ?? 0,
        (input?.offset ?? 0) + (input?.limit ?? 50) - 1
      );

      const { data, error, count } = await query;

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return {
        customers: data ?? [],
        total: count ?? 0,
      };
    }),

  // Get single customer by ID
  getById: customerViewProcedure
    .input(customerIdSchema)
    .query(async ({ ctx, input }) => {
      const { data, error } = await ctx.db
        .from("customers")
        .select("*")
        .eq("id", input.id)
        .eq("organization_id", ctx.organizationId)
        .single();

      if (error) {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "Customer not found",
        });
      }

      return data;
    }),

  // Create new customer
  create: customerEditProcedure
    .input(customerCreateSchema)
    .mutation(async ({ ctx, input }) => {
      const { data, error } = await ctx.db
        .from("customers")
        .insert({
          organization_id: ctx.organizationId,
          name: input.name,
          email: input.email,
          phone: input.phone,
          notes: input.notes,
        })
        .select()
        .single();

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return data;
    }),

  // Update customer
  update: customerEditProcedure
    .input(customerIdSchema.merge(customerUpdateSchema))
    .mutation(async ({ ctx, input }) => {
      const { id, ...updateData } = input;

      const updatePayload: Record<string, unknown> = {
        updated_at: new Date().toISOString(),
      };
      if (updateData.name !== undefined) updatePayload.name = updateData.name;
      if (updateData.email !== undefined) updatePayload.email = updateData.email;
      if (updateData.phone !== undefined) updatePayload.phone = updateData.phone;
      if (updateData.notes !== undefined) updatePayload.notes = updateData.notes;

      const { data, error } = await ctx.db
        .from("customers")
        .update(updatePayload)
        .eq("id", id)
        .eq("organization_id", ctx.organizationId)
        .select()
        .single();

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return data;
    }),

  // Soft delete customer
  delete: customerEditProcedure
    .input(customerIdSchema)
    .mutation(async ({ ctx, input }) => {
      const { error } = await ctx.db
        .from("customers")
        .update({
          deleted_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        })
        .eq("id", input.id)
        .eq("organization_id", ctx.organizationId)
        .is("deleted_at", null);

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return { success: true };
    }),

  // Get customer stats (total customers, new this month, top spenders)
  stats: customerViewProcedure
    .query(async ({ ctx }) => {
      // Total active customers
      const { count: totalCustomers } = await ctx.db
        .from("customers")
        .select("*", { count: "exact", head: true })
        .eq("organization_id", ctx.organizationId)
        .is("deleted_at", null);

      // New this month
      const startOfMonth = new Date();
      startOfMonth.setDate(1);
      startOfMonth.setHours(0, 0, 0, 0);

      const { count: newThisMonth } = await ctx.db
        .from("customers")
        .select("*", { count: "exact", head: true })
        .eq("organization_id", ctx.organizationId)
        .is("deleted_at", null)
        .gte("created_at", startOfMonth.toISOString());

      // Top 5 spenders
      const { data: topSpenders } = await ctx.db
        .from("customers")
        .select("id, name, total_spent, visit_count")
        .eq("organization_id", ctx.organizationId)
        .is("deleted_at", null)
        .order("total_spent", { ascending: false })
        .limit(5);

      return {
        totalCustomers: totalCustomers ?? 0,
        newThisMonth: newThisMonth ?? 0,
        topSpenders: topSpenders ?? [],
      };
    }),
});
