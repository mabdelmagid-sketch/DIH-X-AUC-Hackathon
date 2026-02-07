import { z } from "zod";
import {
  router,
  productViewProcedure,
  productEditProcedure,
  productDeleteProcedure,
} from "../trpc";
import { TRPCError } from "@trpc/server";

// Zod schemas for validation
const productCreateSchema = z.object({
  name: z.string().min(1, "Name is required").max(255),
  description: z.string().max(1000).optional().nullable(),
  sku: z.string().max(100).optional().nullable(),
  barcode: z.string().max(100).optional().nullable(),
  price: z.number().int().min(0, "Price must be positive"),
  cost: z.number().int().min(0).optional().nullable(),
  categoryId: z.string().uuid().optional().nullable(),
  image: z.string().url().optional().nullable(),
  trackInventory: z.boolean().default(false),
  isActive: z.boolean().default(true),
  sortOrder: z.number().int().default(0),
});

const productUpdateSchema = productCreateSchema.partial();

const productIdSchema = z.object({
  id: z.string().uuid(),
});

const listQuerySchema = z.object({
  categoryId: z.string().uuid().optional(),
  isActive: z.boolean().optional(),
  search: z.string().optional(),
  limit: z.number().int().min(1).max(100).default(50),
  offset: z.number().int().min(0).default(0),
});

export const productsRouter = router({
  // Get all products for the organization (excludes soft-deleted)
  list: productViewProcedure
    .input(listQuerySchema.optional())
    .query(async ({ ctx, input }) => {
      let query = ctx.db
        .from("products")
        .select("*, category:categories(*)", { count: "exact" })
        .eq("organization_id", ctx.organizationId)
        .is("deleted_at", null) // Exclude soft-deleted products
        .order("sort_order", { ascending: true })
        .order("name", { ascending: true });

      if (input?.categoryId) {
        query = query.eq("category_id", input.categoryId);
      }

      if (input?.isActive !== undefined) {
        query = query.eq("is_active", input.isActive);
      }

      if (input?.search) {
        query = query.or(
          `name.ilike.%${input.search}%,sku.ilike.%${input.search}%,barcode.ilike.%${input.search}%`
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
        products: data ?? [],
        total: count ?? 0,
      };
    }),

  // Get single product by ID
  getById: productViewProcedure
    .input(productIdSchema)
    .query(async ({ ctx, input }) => {
      const { data, error } = await ctx.db
        .from("products")
        .select("*, category:categories(*)")
        .eq("id", input.id)
        .eq("organization_id", ctx.organizationId)
        .single();

      if (error) {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "Product not found",
        });
      }

      return data;
    }),

  // Get product by barcode
  getByBarcode: productViewProcedure
    .input(z.object({ barcode: z.string() }))
    .query(async ({ ctx, input }) => {
      const { data, error } = await ctx.db
        .from("products")
        .select("*, category:categories(*)")
        .eq("barcode", input.barcode)
        .eq("organization_id", ctx.organizationId)
        .single();

      if (error) {
        return null;
      }

      return data;
    }),

  // Create new product
  create: productEditProcedure
    .input(productCreateSchema)
    .mutation(async ({ ctx, input }) => {
      const { data, error } = await ctx.db
        .from("products")
        .insert({
          organization_id: ctx.organizationId,
          name: input.name,
          description: input.description,
          sku: input.sku,
          barcode: input.barcode,
          price: input.price,
          cost: input.cost,
          category_id: input.categoryId,
          image: input.image,
          track_inventory: input.trackInventory,
          is_active: input.isActive,
          sort_order: input.sortOrder,
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

  // Update product
  update: productEditProcedure
    .input(productIdSchema.merge(productUpdateSchema))
    .mutation(async ({ ctx, input }) => {
      const { id, ...updateData } = input;

      // Build update object with snake_case keys
      const updatePayload: Record<string, unknown> = {};
      if (updateData.name !== undefined) updatePayload.name = updateData.name;
      if (updateData.description !== undefined)
        updatePayload.description = updateData.description;
      if (updateData.sku !== undefined) updatePayload.sku = updateData.sku;
      if (updateData.barcode !== undefined)
        updatePayload.barcode = updateData.barcode;
      if (updateData.price !== undefined) updatePayload.price = updateData.price;
      if (updateData.cost !== undefined) updatePayload.cost = updateData.cost;
      if (updateData.categoryId !== undefined)
        updatePayload.category_id = updateData.categoryId;
      if (updateData.image !== undefined) updatePayload.image = updateData.image;
      if (updateData.trackInventory !== undefined)
        updatePayload.track_inventory = updateData.trackInventory;
      if (updateData.isActive !== undefined)
        updatePayload.is_active = updateData.isActive;
      if (updateData.sortOrder !== undefined)
        updatePayload.sort_order = updateData.sortOrder;

      const { data, error } = await ctx.db
        .from("products")
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

  // Soft delete product (preserves historical order references)
  delete: productDeleteProcedure
    .input(productIdSchema)
    .mutation(async ({ ctx, input }) => {
      const { error } = await ctx.db
        .from("products")
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

  // Bulk update sort order
  updateSortOrder: productEditProcedure
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
          p_table_name: "products",
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

  // Toggle product active status
  toggleActive: productEditProcedure
    .input(productIdSchema)
    .mutation(async ({ ctx, input }) => {
      // Get current status
      const { data: product, error: fetchError } = await ctx.db
        .from("products")
        .select("is_active")
        .eq("id", input.id)
        .eq("organization_id", ctx.organizationId)
        .single();

      if (fetchError || !product) {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "Product not found",
        });
      }

      // Toggle status
      const { data, error } = await ctx.db
        .from("products")
        .update({ is_active: !product.is_active })
        .eq("id", input.id)
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
});
