import { z } from "zod";
import { router, protectedProcedure, adminProcedure } from "../trpc";
import { TRPCError } from "@trpc/server";

// Enum values from database
const unitOfMeasureEnum = z.enum([
  "g", "kg", "mg", "ml", "l", "cl", "oz", "lb", "fl_oz",
  "cup", "tbsp", "tsp", "piece", "each", "slice", "portion", "serving"
]);

const ingredientCategoryEnum = z.enum([
  "DAIRY", "MEAT", "SEAFOOD", "PRODUCE", "GRAINS", "SPICES",
  "BEVERAGES", "OILS", "SAUCES", "BAKING", "FROZEN", "CANNED",
  "DRY_GOODS", "PACKAGING", "CLEANING", "OTHER"
]);

// Schema validators
const ingredientIdSchema = z.object({
  id: z.string().uuid(),
});

const createIngredientSchema = z.object({
  name: z.string().min(1).max(255),
  description: z.string().max(500).optional(),
  sku: z.string().max(50).optional(),
  barcode: z.string().max(50).optional(),
  category: ingredientCategoryEnum.default("OTHER"),
  unit: unitOfMeasureEnum.default("each"),
  costPerUnit: z.number().int().min(0).default(0), // In cents
  minStockLevel: z.number().min(0).default(0),
  reorderQuantity: z.number().min(0).default(0),
  supplierId: z.string().uuid().optional(),
  storageInstructions: z.string().max(500).optional(),
  allergens: z.array(z.string()).default([]),
  isActive: z.boolean().default(true),
});

const updateIngredientSchema = createIngredientSchema.partial().extend({
  id: z.string().uuid(),
});

const listQuerySchema = z.object({
  search: z.string().optional(),
  category: ingredientCategoryEnum.optional(),
  supplierId: z.string().uuid().optional(),
  isActive: z.boolean().optional(),
  lowStockOnly: z.boolean().optional(),
  locationId: z.string().uuid().optional(), // For stock level filtering
  limit: z.number().int().min(1).max(100).default(50),
  offset: z.number().int().min(0).default(0),
});

const stockAdjustmentSchema = z.object({
  ingredientId: z.string().uuid(),
  locationId: z.string().uuid(),
  quantity: z.number(),
  adjustmentType: z.enum([
    "RECEIVE", "SALE", "WASTE", "TRANSFER_IN", "TRANSFER_OUT",
    "COUNT", "RETURN", "PRODUCTION", "CORRECTION", "INITIAL"
  ]),
  reason: z.string().max(500).optional(),
  notes: z.string().max(1000).optional(),
  batchId: z.string().uuid().optional(),
  unitCost: z.number().int().min(0).optional(),
});

const batchSchema = z.object({
  ingredientId: z.string().uuid(),
  locationId: z.string().uuid(),
  quantity: z.number().min(0),
  batchNumber: z.string().max(100).optional(),
  costPerUnit: z.number().int().min(0).optional(),
  expiryDate: z.string().optional(), // ISO date string
  supplierId: z.string().uuid().optional(),
  purchaseOrderId: z.string().uuid().optional(),
  notes: z.string().max(500).optional(),
});

export const ingredientsRouter = router({
  // List all ingredients for the organization (server-side filtering for performance)
  list: protectedProcedure
    .input(listQuerySchema.optional())
    .query(async ({ ctx, input }) => {
      const { data, error } = await (ctx.db.rpc as CallableFunction)(
        "get_ingredients_with_stock",
        {
          p_organization_id: ctx.organizationId,
          p_location_id: input?.locationId ?? null,
          p_category: input?.category ?? null,
          p_supplier_id: input?.supplierId ?? null,
          p_is_active: input?.isActive ?? null,
          p_low_stock_only: input?.lowStockOnly ?? false,
          p_search: input?.search ?? null,
          p_limit: input?.limit ?? 50,
          p_offset: input?.offset ?? 0,
        }
      );

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      const rows = (data ?? []) as Array<{
        id: string;
        name: string;
        description: string | null;
        sku: string | null;
        barcode: string | null;
        category: string;
        unit: string;
        cost_per_unit: number;
        min_stock_level: number;
        reorder_quantity: number;
        supplier_id: string | null;
        storage_instructions: string | null;
        allergens: string[];
        is_active: boolean;
        created_at: string;
        updated_at: string;
        supplier_name: string | null;
        current_stock: number;
        total_count: number;
      }>;

      const ingredients = rows.map((row) => ({
        ...row,
        currentStock: row.current_stock,
        supplier: row.supplier_id ? { id: row.supplier_id, name: row.supplier_name } : null,
      }));

      return {
        ingredients,
        total: rows.length > 0 ? Number(rows[0].total_count) : 0,
      };
    }),

  // Get a single ingredient by ID
  get: protectedProcedure
    .input(ingredientIdSchema)
    .query(async ({ ctx, input }) => {
      const { data, error } = await ctx.db
        .from("ingredients")
        .select("*, supplier:suppliers(*)")
        .eq("id", input.id)
        .eq("organization_id", ctx.organizationId)
        .is("deleted_at", null)
        .single();

      if (error || !data) {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "Ingredient not found",
        });
      }

      return data;
    }),

  // Create a new ingredient
  create: adminProcedure
    .input(createIngredientSchema)
    .mutation(async ({ ctx, input }) => {
      const { data, error } = await ctx.db
        .from("ingredients")
        .insert({
          organization_id: ctx.organizationId,
          name: input.name,
          description: input.description || null,
          sku: input.sku || null,
          barcode: input.barcode || null,
          category: input.category,
          unit: input.unit,
          cost_per_unit: input.costPerUnit,
          min_stock_level: input.minStockLevel,
          reorder_quantity: input.reorderQuantity,
          supplier_id: input.supplierId || null,
          storage_instructions: input.storageInstructions || null,
          allergens: input.allergens,
          is_active: input.isActive,
        })
        .select("*, supplier:suppliers(id, name)")
        .single();

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return data;
    }),

  // Update an existing ingredient
  update: adminProcedure
    .input(updateIngredientSchema)
    .mutation(async ({ ctx, input }) => {
      const { id, ...updateData } = input;

      const updatePayload: Record<string, unknown> = {};
      if (updateData.name !== undefined) updatePayload.name = updateData.name;
      if (updateData.description !== undefined) updatePayload.description = updateData.description;
      if (updateData.sku !== undefined) updatePayload.sku = updateData.sku;
      if (updateData.barcode !== undefined) updatePayload.barcode = updateData.barcode;
      if (updateData.category !== undefined) updatePayload.category = updateData.category;
      if (updateData.unit !== undefined) updatePayload.unit = updateData.unit;
      if (updateData.costPerUnit !== undefined) updatePayload.cost_per_unit = updateData.costPerUnit;
      if (updateData.minStockLevel !== undefined) updatePayload.min_stock_level = updateData.minStockLevel;
      if (updateData.reorderQuantity !== undefined) updatePayload.reorder_quantity = updateData.reorderQuantity;
      if (updateData.supplierId !== undefined) updatePayload.supplier_id = updateData.supplierId || null;
      if (updateData.storageInstructions !== undefined) updatePayload.storage_instructions = updateData.storageInstructions;
      if (updateData.allergens !== undefined) updatePayload.allergens = updateData.allergens;
      if (updateData.isActive !== undefined) updatePayload.is_active = updateData.isActive;

      const { data, error } = await ctx.db
        .from("ingredients")
        .update(updatePayload)
        .eq("id", id)
        .eq("organization_id", ctx.organizationId)
        .is("deleted_at", null)
        .select("*, supplier:suppliers(id, name)")
        .single();

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      if (!data) {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "Ingredient not found",
        });
      }

      return data;
    }),

  // Soft delete an ingredient
  delete: adminProcedure
    .input(ingredientIdSchema)
    .mutation(async ({ ctx, input }) => {
      // Check if ingredient is used in recipes
      const { count: recipeCount } = await ctx.db
        .from("recipe_ingredients")
        .select("id", { count: "exact", head: true })
        .eq("ingredient_id", input.id);

      if (recipeCount && recipeCount > 0) {
        throw new TRPCError({
          code: "PRECONDITION_FAILED",
          message: `Cannot delete ingredient used in ${recipeCount} recipes. Remove from recipes first.`,
        });
      }

      const { error } = await ctx.db
        .from("ingredients")
        .update({ deleted_at: new Date().toISOString() })
        .eq("id", input.id)
        .eq("organization_id", ctx.organizationId);

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return { success: true };
    }),

  // Get stock levels for an ingredient across all locations
  getStock: protectedProcedure
    .input(ingredientIdSchema)
    .query(async ({ ctx, input }) => {
      const { data, error } = await ctx.db
        .from("ingredient_stock")
        .select("*, location:locations(id, name)")
        .eq("ingredient_id", input.id);

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return data ?? [];
    }),

  // Get stock for a specific location
  getStockByLocation: protectedProcedure
    .input(z.object({ locationId: z.string().uuid() }))
    .query(async ({ ctx, input }) => {
      // Get all ingredients for org
      const { data: ingredients } = await ctx.db
        .from("ingredients")
        .select("id")
        .eq("organization_id", ctx.organizationId)
        .is("deleted_at", null);

      const ingredientIds = (ingredients ?? []).map((i) => i.id);
      if (ingredientIds.length === 0) return [];

      const { data, error } = await ctx.db
        .from("ingredient_stock")
        .select("*, ingredient:ingredients(*)")
        .eq("location_id", input.locationId)
        .in("ingredient_id", ingredientIds);

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return data ?? [];
    }),

  // Adjust stock level (atomic - updates stock and creates audit in single transaction)
  adjustStock: protectedProcedure
    .input(stockAdjustmentSchema)
    .mutation(async ({ ctx, input }) => {
      const { data, error } = await (ctx.db.rpc as CallableFunction)(
        "adjust_ingredient_stock_atomic",
        {
          p_ingredient_id: input.ingredientId,
          p_location_id: input.locationId,
          p_quantity: input.quantity,
          p_adjustment_type: input.adjustmentType,
          p_reason: input.reason || null,
          p_notes: input.notes || null,
          p_batch_id: input.batchId || null,
          p_unit_cost: input.unitCost || null,
          p_user_id: ctx.user.id,
          p_organization_id: ctx.organizationId,
        }
      );

      if (error) {
        if (error.code === "P0004") {
          throw new TRPCError({
            code: "BAD_REQUEST",
            message: "Cannot reduce stock below zero",
          });
        }
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return {
        adjustment: null, // Audit record created inside DB function
        newQuantity: data as number,
      };
    }),

  // Get adjustment history for an ingredient
  getAdjustmentHistory: protectedProcedure
    .input(
      z.object({
        ingredientId: z.string().uuid().optional(),
        locationId: z.string().uuid().optional(),
        adjustmentType: stockAdjustmentSchema.shape.adjustmentType.optional(),
        limit: z.number().int().min(1).max(100).default(50),
        offset: z.number().int().min(0).default(0),
      })
    )
    .query(async ({ ctx, input }) => {
      let query = ctx.db
        .from("inventory_adjustments")
        .select("*, ingredient:ingredients(name), adjusted_by_user:users(name)", { count: "exact" })
        .eq("organization_id", ctx.organizationId)
        .order("created_at", { ascending: false });

      if (input.ingredientId) {
        query = query.eq("ingredient_id", input.ingredientId);
      }

      if (input.locationId) {
        query = query.eq("location_id", input.locationId);
      }

      if (input.adjustmentType) {
        query = query.eq("adjustment_type", input.adjustmentType);
      }

      const { data, error, count } = await query
        .range(input.offset, input.offset + input.limit - 1);

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return {
        adjustments: data ?? [],
        total: count ?? 0,
      };
    }),

  // Add a new batch with expiry tracking (atomic - creates batch, updates stock, records adjustment)
  addBatch: protectedProcedure
    .input(batchSchema)
    .mutation(async ({ ctx, input }) => {
      const { data, error } = await (ctx.db.rpc as CallableFunction)(
        "add_ingredient_batch_atomic",
        {
          p_ingredient_id: input.ingredientId,
          p_location_id: input.locationId,
          p_quantity: input.quantity,
          p_batch_number: input.batchNumber || null,
          p_cost_per_unit: input.costPerUnit ?? null,
          p_expiry_date: input.expiryDate || null,
          p_supplier_id: input.supplierId || null,
          p_purchase_order_id: input.purchaseOrderId || null,
          p_notes: input.notes || null,
          p_user_id: ctx.user.id,
          p_organization_id: ctx.organizationId,
        }
      );

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      // Fetch the created batch to return it
      const { data: batch, error: fetchError } = await ctx.db
        .from("inventory_batches")
        .select("*")
        .eq("id", data)
        .single();

      if (fetchError) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: fetchError.message,
        });
      }

      return batch;
    }),

  // Get batches for an ingredient (with expiry info)
  getBatches: protectedProcedure
    .input(
      z.object({
        ingredientId: z.string().uuid().optional(),
        locationId: z.string().uuid().optional(),
        includeExpired: z.boolean().default(false),
        includeDisposed: z.boolean().default(false),
      })
    )
    .query(async ({ ctx, input }) => {
      // Get ingredient IDs for this org
      const { data: ingredients } = await ctx.db
        .from("ingredients")
        .select("id")
        .eq("organization_id", ctx.organizationId)
        .is("deleted_at", null);

      const ingredientIds = (ingredients ?? []).map((i) => i.id);
      if (ingredientIds.length === 0) return [];

      let query = ctx.db
        .from("inventory_batches")
        .select("*, ingredient:ingredients(name, unit), supplier:suppliers(name)")
        .in("ingredient_id", ingredientIds)
        .order("expiry_date", { ascending: true, nullsFirst: false });

      if (input.ingredientId) {
        query = query.eq("ingredient_id", input.ingredientId);
      }

      if (input.locationId) {
        query = query.eq("location_id", input.locationId);
      }

      if (!input.includeDisposed) {
        query = query.is("disposed_at", null);
      }

      if (!input.includeExpired) {
        query = query.eq("is_expired", false);
      }

      const { data, error } = await query;

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return data ?? [];
    }),

  // Get expiring batches (using database function)
  getExpiringBatches: protectedProcedure
    .input(
      z.object({
        locationId: z.string().uuid(),
        daysThreshold: z.number().int().min(1).max(365).default(7),
      })
    )
    .query(async ({ ctx, input }) => {
      const { data, error } = await ctx.db.rpc("get_expiring_batches", {
        p_location_id: input.locationId,
        p_days_threshold: input.daysThreshold,
      });

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return data ?? [];
    }),

  // Get low stock ingredients (using database function)
  getLowStock: protectedProcedure
    .input(z.object({ locationId: z.string().uuid() }))
    .query(async ({ ctx, input }) => {
      const { data, error } = await ctx.db.rpc("get_low_stock_ingredients", {
        p_location_id: input.locationId,
      });

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return data ?? [];
    }),

  // Mark batch as waste/disposed (atomic - updates batch, stock, and audit in single transaction)
  disposeBatch: protectedProcedure
    .input(
      z.object({
        batchId: z.string().uuid(),
        reason: z.string().max(500),
        quantity: z.number().optional(), // If not provided, dispose entire batch
      })
    )
    .mutation(async ({ ctx, input }) => {
      const { data, error } = await (ctx.db.rpc as CallableFunction)(
        "dispose_batch_atomic",
        {
          p_batch_id: input.batchId,
          p_reason: input.reason,
          p_quantity: input.quantity ?? null,
          p_user_id: ctx.user.id,
          p_organization_id: ctx.organizationId,
        }
      );

      if (error) {
        if (error.code === "P0002") {
          throw new TRPCError({
            code: "NOT_FOUND",
            message: "Batch not found",
          });
        }
        if (error.code === "P0004") {
          throw new TRPCError({
            code: "BAD_REQUEST",
            message: "Cannot dispose more than available quantity",
          });
        }
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return { success: true, disposed: input.quantity ?? 0 };
    }),

  // Get ingredient categories summary
  getCategorySummary: protectedProcedure.query(async ({ ctx }) => {
    const { data, error } = await ctx.db
      .from("ingredients")
      .select("category")
      .eq("organization_id", ctx.organizationId)
      .is("deleted_at", null);

    if (error) {
      throw new TRPCError({
        code: "INTERNAL_SERVER_ERROR",
        message: error.message,
      });
    }

    // Count by category
    const categoryCounts: Record<string, number> = {};
    for (const item of data ?? []) {
      const category = item.category ?? "OTHER";
      categoryCounts[category] = (categoryCounts[category] ?? 0) + 1;
    }

    return categoryCounts;
  }),
});
