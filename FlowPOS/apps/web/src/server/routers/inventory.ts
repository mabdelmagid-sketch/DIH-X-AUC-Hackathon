import { z } from "zod";
import { router, protectedProcedure, adminProcedure } from "../trpc";
import { TRPCError } from "@trpc/server";

const inventoryIdSchema = z.object({
  id: z.string().uuid(),
});

const listQuerySchema = z.object({
  locationId: z.string().uuid().optional(),
  lowStockOnly: z.boolean().optional(),
  productId: z.string().uuid().optional(),
  search: z.string().optional(),
  limit: z.number().int().min(1).max(100).default(50),
  offset: z.number().int().min(0).default(0),
});

export const inventoryRouter = router({
  // Get all inventory items for the organization (server-side filtering for performance)
  list: protectedProcedure
    .input(listQuerySchema.optional())
    .query(async ({ ctx, input }) => {
      const { data, error } = await (ctx.db.rpc as CallableFunction)(
        "get_inventory_items",
        {
          p_organization_id: ctx.organizationId,
          p_location_id: input?.locationId ?? null,
          p_product_id: input?.productId ?? null,
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
        product_id: string;
        location_id: string;
        quantity: number;
        low_stock: number;
        updated_at: string;
        product_name: string;
        product_sku: string | null;
        product_barcode: string | null;
        product_price: number;
        product_image: string | null;
        product_is_active: boolean;
        location_name: string;
        total_count: number;
      }>;

      // Reshape to match existing response format
      const items = rows.map((row) => ({
        id: row.id,
        product_id: row.product_id,
        location_id: row.location_id,
        quantity: row.quantity,
        low_stock: row.low_stock,
        updated_at: row.updated_at,
        product: {
          id: row.product_id,
          name: row.product_name,
          sku: row.product_sku,
          barcode: row.product_barcode,
          price: row.product_price,
          image: row.product_image,
          is_active: row.product_is_active,
        },
        location: {
          id: row.location_id,
          name: row.location_name,
        },
      }));

      return {
        items,
        total: rows.length > 0 ? Number(rows[0].total_count) : 0,
      };
    }),

  // Get inventory for a specific product across all locations
  getByProduct: protectedProcedure
    .input(z.object({ productId: z.string().uuid() }))
    .query(async ({ ctx, input }) => {
      const { data, error } = await ctx.db
        .from("inventory_items")
        .select("*, location:locations(*)")
        .eq("product_id", input.productId);

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return data ?? [];
    }),

  // Get inventory for a specific location
  getByLocation: protectedProcedure
    .input(z.object({ locationId: z.string().uuid() }))
    .query(async ({ ctx, input }) => {
      // Get products for org
      const { data: products } = await ctx.db
        .from("products")
        .select("id")
        .eq("organization_id", ctx.organizationId)
        .eq("track_inventory", true);

      const productIds = (products ?? []).map((p) => p.id);

      if (productIds.length === 0) {
        return [];
      }

      const { data, error } = await ctx.db
        .from("inventory_items")
        .select("*, product:products(*)")
        .eq("location_id", input.locationId)
        .in("product_id", productIds);

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return data ?? [];
    }),

  // Get low stock items
  getLowStock: protectedProcedure
    .input(z.object({ locationId: z.string().uuid().optional() }))
    .query(async ({ ctx, input }) => {
      // Get products for org
      const { data: products } = await ctx.db
        .from("products")
        .select("id")
        .eq("organization_id", ctx.organizationId)
        .eq("track_inventory", true);

      const productIds = (products ?? []).map((p) => p.id);

      if (productIds.length === 0) {
        return [];
      }

      let query = ctx.db
        .from("inventory_items")
        .select("*, product:products(*), location:locations(*)")
        .in("product_id", productIds);

      if (input.locationId) {
        query = query.eq("location_id", input.locationId);
      }

      const { data, error } = await query;

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      // Filter to low stock items only
      const lowStockItems = (data ?? []).filter(
        (item) => (item.quantity ?? 0) <= (item.low_stock ?? 10)
      );

      return lowStockItems;
    }),

  // Set inventory level (create or update)
  setLevel: adminProcedure
    .input(
      z.object({
        productId: z.string().uuid(),
        locationId: z.string().uuid(),
        quantity: z.number().int().min(0),
        lowStock: z.number().int().min(0).optional(),
      })
    )
    .mutation(async ({ ctx, input }) => {
      // Check if inventory item exists
      const { data: existing } = await ctx.db
        .from("inventory_items")
        .select("id")
        .eq("product_id", input.productId)
        .eq("location_id", input.locationId)
        .single();

      if (existing) {
        // Update existing
        const updatePayload: Record<string, unknown> = {
          quantity: input.quantity,
        };
        if (input.lowStock !== undefined) {
          updatePayload.low_stock = input.lowStock;
        }

        const { data, error } = await ctx.db
          .from("inventory_items")
          .update(updatePayload)
          .eq("id", existing.id)
          .select("*, product:products(*), location:locations(*)")
          .single();

        if (error) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: error.message,
          });
        }

        return data;
      } else {
        // Create new
        const { data, error } = await ctx.db
          .from("inventory_items")
          .insert({
            product_id: input.productId,
            location_id: input.locationId,
            quantity: input.quantity,
            low_stock: input.lowStock ?? 10,
          })
          .select("*, product:products(*), location:locations(*)")
          .single();

        if (error) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: error.message,
          });
        }

        return data;
      }
    }),

  // Adjust inventory (add or subtract)
  adjust: adminProcedure
    .input(
      z.object({
        productId: z.string().uuid(),
        locationId: z.string().uuid(),
        adjustment: z.number().int(), // Positive or negative
        reason: z.string().max(500).optional(),
      })
    )
    .mutation(async ({ ctx, input }) => {
      // Get current inventory
      const { data: existing, error: fetchError } = await ctx.db
        .from("inventory_items")
        .select("id, quantity")
        .eq("product_id", input.productId)
        .eq("location_id", input.locationId)
        .single();

      if (fetchError || !existing) {
        // Create new inventory record if doesn't exist
        if (input.adjustment < 0) {
          throw new TRPCError({
            code: "BAD_REQUEST",
            message: "Cannot reduce inventory below zero",
          });
        }

        const { data, error } = await ctx.db
          .from("inventory_items")
          .insert({
            product_id: input.productId,
            location_id: input.locationId,
            quantity: input.adjustment,
          })
          .select("*, product:products(*), location:locations(*)")
          .single();

        if (error) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: error.message,
          });
        }

        return data;
      }

      const newQuantity = (existing.quantity ?? 0) + input.adjustment;

      if (newQuantity < 0) {
        throw new TRPCError({
          code: "BAD_REQUEST",
          message: "Cannot reduce inventory below zero",
        });
      }

      const { data, error } = await ctx.db
        .from("inventory_items")
        .update({ quantity: newQuantity })
        .eq("id", existing.id)
        .select("*, product:products(*), location:locations(*)")
        .single();

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return data;
    }),

  // Bulk adjust inventory (atomic - all-or-nothing with row locking)
  bulkAdjust: protectedProcedure
    .input(
      z.object({
        locationId: z.string().uuid(),
        items: z.array(
          z.object({
            productId: z.string().uuid(),
            adjustment: z.number().int(),
          })
        ),
      })
    )
    .mutation(async ({ ctx, input }) => {
      const { data, error } = await (ctx.db.rpc as CallableFunction)(
        "bulk_adjust_inventory",
        {
          p_location_id: input.locationId,
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

      const results = (data as Array<{ productId: string; newQuantity: number }>).map(
        (r) => ({ productId: r.productId, success: true, newQuantity: r.newQuantity })
      );

      return {
        results,
        summary: {
          total: input.items.length,
          successful: results.length,
          failed: 0,
        },
      };
    }),

  // Update low stock threshold
  updateLowStockThreshold: adminProcedure
    .input(
      z.object({
        id: z.string().uuid(),
        lowStock: z.number().int().min(0),
      })
    )
    .mutation(async ({ ctx, input }) => {
      const { data, error } = await ctx.db
        .from("inventory_items")
        .update({ low_stock: input.lowStock })
        .eq("id", input.id)
        .select("*, product:products(*), location:locations(*)")
        .single();

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return data;
    }),

  // Get inventory statistics
  getStats: protectedProcedure
    .input(z.object({ locationId: z.string().uuid().optional() }))
    .query(async ({ ctx, input }) => {
      // Get products for org
      const { data: products } = await ctx.db
        .from("products")
        .select("id, price, cost")
        .eq("organization_id", ctx.organizationId)
        .eq("track_inventory", true);

      const productIds = (products ?? []).map((p) => p.id);

      if (productIds.length === 0) {
        return {
          totalProducts: 0,
          totalQuantity: 0,
          lowStockCount: 0,
          outOfStockCount: 0,
          totalValue: 0,
        };
      }

      let query = ctx.db
        .from("inventory_items")
        .select("product_id, quantity, low_stock")
        .in("product_id", productIds);

      if (input.locationId) {
        query = query.eq("location_id", input.locationId);
      }

      const { data, error } = await query;

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      const items = data ?? [];
      const productMap = new Map(
        (products ?? []).map((p) => [p.id, { price: p.price, cost: p.cost }])
      );

      let totalQuantity = 0;
      let lowStockCount = 0;
      let outOfStockCount = 0;
      let totalValue = 0;

      for (const item of items) {
        const qty = item.quantity ?? 0;
        totalQuantity += qty;

        if (qty === 0) {
          outOfStockCount++;
        } else if (qty <= (item.low_stock ?? 10)) {
          lowStockCount++;
        }

        const product = productMap.get(item.product_id);
        if (product) {
          totalValue += qty * (product.cost ?? product.price);
        }
      }

      return {
        totalProducts: items.length,
        totalQuantity,
        lowStockCount,
        outOfStockCount,
        totalValue,
      };
    }),
});
