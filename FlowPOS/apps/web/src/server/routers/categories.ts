import { z } from "zod";
import { router, protectedProcedure, adminProcedure } from "../trpc";
import { TRPCError } from "@trpc/server";

// Zod schemas for validation
const categoryCreateSchema = z.object({
  name: z.string().min(1, "Name is required").max(100),
  description: z.string().max(500).optional().nullable(),
  color: z
    .string()
    .regex(/^#[0-9A-Fa-f]{6}$/, "Invalid hex color")
    .optional()
    .nullable(),
  sortOrder: z.number().int().default(0),
  isActive: z.boolean().default(true),
});

const categoryUpdateSchema = categoryCreateSchema.partial();

const categoryIdSchema = z.object({
  id: z.string().uuid(),
});

export const categoriesRouter = router({
  // Get all categories for the organization (excludes soft-deleted)
  list: protectedProcedure.query(async ({ ctx }) => {
    const { data, error } = await ctx.db
      .from("categories")
      .select("*")
      .eq("organization_id", ctx.organizationId)
      .is("deleted_at", null) // Exclude soft-deleted categories
      .order("sort_order", { ascending: true })
      .order("name", { ascending: true });

    if (error) {
      throw new TRPCError({
        code: "INTERNAL_SERVER_ERROR",
        message: error.message,
      });
    }

    return data ?? [];
  }),

  // Get single category by ID
  getById: protectedProcedure
    .input(categoryIdSchema)
    .query(async ({ ctx, input }) => {
      const { data, error } = await ctx.db
        .from("categories")
        .select("*")
        .eq("id", input.id)
        .eq("organization_id", ctx.organizationId)
        .single();

      if (error) {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "Category not found",
        });
      }

      return data;
    }),

  // Get category with products
  getWithProducts: protectedProcedure
    .input(categoryIdSchema)
    .query(async ({ ctx, input }) => {
      const { data, error } = await ctx.db
        .from("categories")
        .select("*, products(*)")
        .eq("id", input.id)
        .eq("organization_id", ctx.organizationId)
        .single();

      if (error) {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "Category not found",
        });
      }

      return data;
    }),

  // Create new category
  create: adminProcedure
    .input(categoryCreateSchema)
    .mutation(async ({ ctx, input }) => {
      const { data, error } = await ctx.db
        .from("categories")
        .insert({
          organization_id: ctx.organizationId,
          name: input.name,
          description: input.description,
          color: input.color,
          sort_order: input.sortOrder,
          is_active: input.isActive,
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

  // Update category
  update: adminProcedure
    .input(categoryIdSchema.merge(categoryUpdateSchema))
    .mutation(async ({ ctx, input }) => {
      const { id, ...updateData } = input;

      const updatePayload: Record<string, unknown> = {};
      if (updateData.name !== undefined) updatePayload.name = updateData.name;
      if (updateData.description !== undefined)
        updatePayload.description = updateData.description;
      if (updateData.color !== undefined) updatePayload.color = updateData.color;
      if (updateData.sortOrder !== undefined)
        updatePayload.sort_order = updateData.sortOrder;
      if (updateData.isActive !== undefined)
        updatePayload.is_active = updateData.isActive;

      const { data, error } = await ctx.db
        .from("categories")
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

  // Soft delete category (preserves historical references)
  delete: adminProcedure
    .input(categoryIdSchema)
    .mutation(async ({ ctx, input }) => {
      // Note: Products keep their category_id for historical reference
      // They just won't appear under this category in the UI anymore
      const { error } = await ctx.db
        .from("categories")
        .update({
          deleted_at: new Date().toISOString(),
          is_active: false,
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

  // Update sort order for multiple categories
  updateSortOrder: adminProcedure
    .input(
      z.object({
        items: z.array(
          z.object({
            id: z.string().uuid(),
            sortOrder: z.number().int(),
          })
        ),
      })
    )
    .mutation(async ({ ctx, input }) => {
      const { error } = await (ctx.db.rpc as CallableFunction)(
        "bulk_update_sort_order",
        {
          p_table_name: "categories",
          p_items: JSON.stringify(input.items),
          p_organization_id: ctx.organizationId,
        }
      );

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return { success: true };
    }),
});
