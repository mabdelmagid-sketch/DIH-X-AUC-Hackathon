import { z } from "zod";
import {
  router,
  orderViewProcedure,
  orderCreateProcedure,
  orderEditProcedure,
  kitchenViewProcedure,
  reportViewProcedure,
  createPermissionProcedure,
} from "../trpc";
import { TRPCError } from "@trpc/server";
import { logger } from "@/lib/logger";

// Special procedures for specific order permissions
const orderVoidProcedure = createPermissionProcedure("pos:void");
const orderRefundProcedure = createPermissionProcedure("pos:refund");

// Enums as Zod schemas
const orderStatusSchema = z.enum([
  "OPEN",
  "IN_PROGRESS",
  "READY",
  "COMPLETED",
  "CANCELLED",
  "REFUNDED",
]);

const orderTypeSchema = z.enum(["DINE_IN", "TAKEOUT", "DELIVERY", "CAREEM", "TALABAT"]);

const itemStatusSchema = z.enum([
  "PENDING",
  "PREPARING",
  "READY",
  "DELIVERED",
  "CANCELLED",
]);

const paymentMethodSchema = z.enum([
  "CASH",
  "CARD",
  "MOBILE",
  "GIFT_CARD",
  "STORE_CREDIT",
  "OTHER",
]);

// Order item schema
const orderItemSchema = z.object({
  productId: z.string().uuid(),
  variantId: z.string().uuid().optional().nullable(),
  name: z.string(),
  quantity: z.number().int().positive(),
  unitPrice: z.number().int().min(0),
  totalPrice: z.number().int().min(0),
  notes: z.string().optional().nullable(),
  modifiers: z
    .array(
      z.object({
        modifierId: z.string().uuid(),
        name: z.string(),
        price: z.number().int().min(0),
      })
    )
    .optional(),
});

// Payment schema
const paymentSchema = z.object({
  method: paymentMethodSchema,
  amount: z.number().int().positive(),
  tipAmount: z.number().int().min(0).default(0),
  reference: z.string().optional().nullable(),
});

// Order create schema
const orderCreateSchema = z.object({
  locationId: z.string().uuid(),
  terminalId: z.string().uuid().optional().nullable(),
  customerId: z.string().uuid().optional().nullable(),
  tableId: z.string().uuid().optional().nullable(),
  type: orderTypeSchema.default("DINE_IN"),
  items: z.array(orderItemSchema).min(1, "Order must have at least one item"),
  notes: z.string().max(500).optional().nullable(),
  discountAmount: z.number().int().min(0).default(0),
  taxAmount: z.number().int().min(0).default(0),
  tipAmount: z.number().int().min(0).default(0),
});

const orderIdSchema = z.object({
  id: z.string().uuid(),
});

const listQuerySchema = z.object({
  status: orderStatusSchema.optional(),
  type: orderTypeSchema.optional(),
  locationId: z.string().uuid().optional(),
  customerId: z.string().uuid().optional(),
  employeeId: z.string().uuid().optional(),
  tableId: z.string().uuid().optional(),
  dateFrom: z.string().datetime().optional(),
  dateTo: z.string().datetime().optional(),
  limit: z.number().int().min(1).max(100).default(50),
  offset: z.number().int().min(0).default(0),
});

export const ordersRouter = router({
  // Get all orders for the organization
  list: orderViewProcedure
    .input(listQuerySchema.optional())
    .query(async ({ ctx, input }) => {
      let query = ctx.db
        .from("orders")
        .select(
          "*, customer:customers(*), employee:employees(*, user:users(*)), table:tables(*), items:order_items(*, modifiers:order_item_modifiers(*))",
          { count: "exact" }
        )
        .eq("organization_id", ctx.organizationId)
        .order("created_at", { ascending: false });

      if (input?.status) {
        query = query.eq("status", input.status);
      }

      if (input?.type) {
        query = query.eq("type", input.type);
      }

      if (input?.locationId) {
        query = query.eq("location_id", input.locationId);
      }

      if (input?.customerId) {
        query = query.eq("customer_id", input.customerId);
      }

      if (input?.employeeId) {
        query = query.eq("employee_id", input.employeeId);
      }

      if (input?.tableId) {
        query = query.eq("table_id", input.tableId);
      }

      if (input?.dateFrom) {
        query = query.gte("created_at", input.dateFrom);
      }

      if (input?.dateTo) {
        query = query.lte("created_at", input.dateTo);
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
        orders: data ?? [],
        total: count ?? 0,
      };
    }),

  // Get single order by ID with all details
  getById: orderViewProcedure
    .input(orderIdSchema)
    .query(async ({ ctx, input }) => {
      const { data, error } = await ctx.db
        .from("orders")
        .select(
          "*, customer:customers(*), employee:employees(*, user:users(*)), table:tables(*), items:order_items(*, modifiers:order_item_modifiers(*))"
        )
        .eq("id", input.id)
        .eq("organization_id", ctx.organizationId)
        .single();

      if (error) {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "Order not found",
        });
      }

      return data;
    }),

  // Get orders for KDS (kitchen display)
  getForKDS: kitchenViewProcedure
    .input(
      z.object({
        locationId: z.string().uuid(),
        statuses: z.array(orderStatusSchema).optional(),
      })
    )
    .query(async ({ ctx, input }) => {
      let query = ctx.db
        .from("orders")
        .select("*, table:tables(*), items:order_items(*, modifiers:order_item_modifiers(*))")
        .eq("organization_id", ctx.organizationId)
        .eq("location_id", input.locationId)
        .order("created_at", { ascending: true });

      if (input.statuses && input.statuses.length > 0) {
        query = query.in("status", input.statuses);
      } else {
        // Default to active orders
        query = query.in("status", ["OPEN", "IN_PROGRESS", "READY"]);
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

  // Get next order number
  getNextOrderNumber: orderCreateProcedure
    .input(z.object({ locationId: z.string().uuid() }))
    .query(async ({ ctx }) => {
      const { data, error } = await ctx.db
        .from("orders")
        .select("order_number")
        .eq("organization_id", ctx.organizationId)
        .order("order_number", { ascending: false })
        .limit(1)
        .single();

      if (error && error.code !== "PGRST116") {
        // PGRST116 = no rows found
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return { nextOrderNumber: (data?.order_number ?? 0) + 1 };
    }),

  // Create new order (uses transactional database function for atomicity)
  create: orderCreateProcedure
    .input(orderCreateSchema)
    .mutation(async ({ ctx, input }) => {
      // Get employee ID from current user
      const { data: employee } = await ctx.db
        .from("employees")
        .select("id")
        .eq("user_id", ctx.user.id)
        .single();

      // 1. Fetch real prices from database to prevent client-side price tampering
      const productIds = input.items.map((item) => item.productId);
      const { data: products, error: productsError } = await ctx.db
        .from("products")
        .select("id, price")
        .in("id", productIds);

      if (productsError || !products) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: "Failed to verify product prices",
        });
      }

      const priceMap = new Map(products.map((p) => [p.id, p.price]));

      // Fetch modifier prices from database to prevent client-side price tampering
      const allModifierIds = input.items.flatMap(
        (item) => (item.modifiers || []).map((m) => m.modifierId)
      );
      const modifierPriceMap = new Map<string, number>();
      if (allModifierIds.length > 0) {
        const { data: dbModifiers, error: modError } = await ctx.db
          .from("modifiers")
          .select("id, price")
          .in("id", allModifierIds);

        if (modError) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: "Failed to verify modifier prices",
          });
        }

        for (const mod of dbModifiers ?? []) {
          modifierPriceMap.set(mod.id, mod.price);
        }
      }

      // 2. Recalculate totals using server prices
      let subtotal = 0;
      const validatedItems = input.items.map((item) => {
        const dbPrice = priceMap.get(item.productId);
        if (dbPrice === undefined) {
          throw new TRPCError({
            code: "BAD_REQUEST",
            message: `Product ${item.productId} not found`,
          });
        }

        // Use server-side modifier prices instead of client-provided prices
        const validatedModifiers = (item.modifiers || []).map((m) => {
          const dbModPrice = modifierPriceMap.get(m.modifierId);
          if (dbModPrice === undefined) {
            throw new TRPCError({
              code: "BAD_REQUEST",
              message: `Modifier ${m.modifierId} not found`,
            });
          }
          return { ...m, price: dbModPrice };
        });
        const modifierTotal = validatedModifiers.reduce((sum, m) => sum + m.price, 0);
        const unitPrice = dbPrice;
        const itemTotalPrice = (unitPrice + modifierTotal) * item.quantity;

        subtotal += itemTotalPrice;

        return {
          productId: item.productId,
          variantId: item.variantId ?? null,
          name: item.name,
          quantity: item.quantity,
          unitPrice: unitPrice,
          totalPrice: itemTotalPrice,
          notes: item.notes ?? null,
          modifiers: validatedModifiers,
        };
      });

      const total =
        subtotal - input.discountAmount + input.taxAmount + input.tipAmount;

      // Use transactional function to create order with items atomically
      const { data, error } = await (ctx.db.rpc as CallableFunction)(
        "create_order_with_items",
        {
          p_organization_id: ctx.organizationId,
          p_location_id: input.locationId,
          p_terminal_id: input.terminalId ?? null,
          p_customer_id: input.customerId ?? null,
          p_table_id: input.tableId ?? null,
          p_employee_id: employee?.id ?? null,
          p_type: input.type,
          p_subtotal: subtotal,
          p_discount_amount: input.discountAmount,
          p_tax_amount: input.taxAmount,
          p_tip_amount: input.tipAmount,
          p_total: total,
          p_notes: input.notes ?? null,
          p_items: validatedItems,
        }
      );

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: `Failed to create order: ${error.message}`,
        });
      }

      return data;
    }),

  // Checkout order with payments (ATOMIC - uses database function)
  checkout: orderEditProcedure
    .input(
      z.object({
        orderId: z.string().uuid(),
        payments: z.array(paymentSchema).min(1, "At least one payment is required"),
        status: orderStatusSchema.default("COMPLETED"),
      })
    )
    .mutation(async ({ ctx, input }) => {
      // Use atomic checkout function to prevent ghost payments
      // After migration 20260114_fix_atomic_inventory_deduction.sql, this function
      // also handles inventory deduction atomically in the database transaction
      const { data, error } = await (ctx.db.rpc as CallableFunction)(
        "checkout_order",
        {
          p_order_id: input.orderId,
          p_organization_id: ctx.organizationId,
          p_payments: input.payments.map((p) => ({
            method: p.method,
            amount: p.amount,
            tipAmount: p.tipAmount,
            reference: p.reference ?? null,
          })),
          p_status: input.status,
        }
      );

      if (error) {
        // Map database error codes to user-friendly messages
        if (error.code === "P0002") {
          throw new TRPCError({
            code: "NOT_FOUND",
            message: "Order not found",
          });
        }
        if (error.code === "P0003") {
          throw new TRPCError({
            code: "BAD_REQUEST",
            message: error.message || "Order already finalized",
          });
        }
        if (error.code === "P0004") {
          throw new TRPCError({
            code: "BAD_REQUEST",
            message: error.message || "Insufficient payment",
          });
        }
        if (error.code === "P0005") {
          // NEW: Inventory deduction error from updated checkout_order function
          throw new TRPCError({
            code: "BAD_REQUEST",
            message: error.message || "Failed to update inventory. Please check stock levels.",
          });
        }
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: `Failed to checkout order: ${error.message}`,
        });
      }

      // Inventory deduction is handled atomically by the checkout_order DB function
      // (returns inventoryDeducted: true). No application-level fallback needed.

      return data;
    }),

  // Update specific order item status
  updateItemStatus: kitchenViewProcedure
    .input(
      z.object({
        orderId: z.string().uuid(),
        itemId: z.string().uuid(),
        status: itemStatusSchema,
      })
    )
    .mutation(async ({ ctx, input }) => {
      const { data, error } = await ctx.db
        .from("order_items")
        .update({
          status: input.status,
        })
        .eq("id", input.itemId)
        .eq("order_id", input.orderId)
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

  // Update order status
  updateStatus: orderEditProcedure
    .input(
      z.object({
        id: z.string().uuid(),
        status: orderStatusSchema,
      })
    )
    .mutation(async ({ ctx, input }) => {
      const updatePayload: Record<string, unknown> = {
        status: input.status,
      };

      if (input.status === "COMPLETED") {
        updatePayload.completed_at = new Date().toISOString();
      }

      const { data, error } = await ctx.db
        .from("orders")
        .update(updatePayload)
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

  // Update order (for modifications before completion)
  update: orderEditProcedure
    .input(
      orderIdSchema.merge(
        z.object({
          customerId: z.string().uuid().optional().nullable(),
          tableId: z.string().uuid().optional().nullable(),
          notes: z.string().max(500).optional().nullable(),
          discountAmount: z.number().int().min(0).optional(),
          tipAmount: z.number().int().min(0).optional(),
        })
      )
    )
    .mutation(async ({ ctx, input }) => {
      const { id, ...updateData } = input;

      const updatePayload: Record<string, unknown> = {};
      if (updateData.customerId !== undefined)
        updatePayload.customer_id = updateData.customerId;
      if (updateData.tableId !== undefined)
        updatePayload.table_id = updateData.tableId;
      if (updateData.notes !== undefined) updatePayload.notes = updateData.notes;
      if (updateData.discountAmount !== undefined)
        updatePayload.discount_amount = updateData.discountAmount;
      if (updateData.tipAmount !== undefined)
        updatePayload.tip_amount = updateData.tipAmount;

      const { data, error } = await ctx.db
        .from("orders")
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

  // Void/cancel order
  void: orderVoidProcedure
    .input(
      z.object({
        id: z.string().uuid(),
        reason: z.string().min(1).max(500),
      })
    )
    .mutation(async ({ ctx, input }) => {
      const { data, error } = await ctx.db
        .from("orders")
        .update({
          status: "CANCELLED",
          notes: `VOIDED: ${input.reason}`,
        })
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

  // Refund order
  refund: orderRefundProcedure
    .input(
      z.object({
        id: z.string().uuid(),
        reason: z.string().min(1).max(500),
        amount: z.number().int().positive().optional(), // Partial refund amount, or full if not specified
      })
    )
    .mutation(async ({ ctx, input }) => {
      const { data, error } = await ctx.db
        .from("orders")
        .update({
          status: "REFUNDED",
          notes: `REFUNDED: ${input.reason}${input.amount ? ` (Amount: ${input.amount})` : ""}`,
        })
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

  // Get order statistics
  getStats: reportViewProcedure
    .input(
      z.object({
        locationId: z.string().uuid().optional(),
        dateFrom: z.string().datetime().optional(),
        dateTo: z.string().datetime().optional(),
      })
    )
    .query(async ({ ctx, input }) => {
      let query = ctx.db
        .from("orders")
        .select("status, total, type")
        .eq("organization_id", ctx.organizationId);

      if (input.locationId) {
        query = query.eq("location_id", input.locationId);
      }

      if (input.dateFrom) {
        query = query.gte("created_at", input.dateFrom);
      }

      if (input.dateTo) {
        query = query.lte("created_at", input.dateTo);
      }

      const { data, error } = await query;

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      const orders = data ?? [];
      const totalOrders = orders.length;
      const completedOrders = orders.filter((o) => o.status === "COMPLETED").length;
      const cancelledOrders = orders.filter((o) => o.status === "CANCELLED").length;
      const totalRevenue = orders
        .filter((o) => o.status === "COMPLETED")
        .reduce((sum, o) => sum + (o.total ?? 0), 0);

      const byType = {
        DINE_IN: orders.filter((o) => o.type === "DINE_IN").length,
        TAKEOUT: orders.filter((o) => o.type === "TAKEOUT").length,
        DELIVERY: orders.filter((o) => o.type === "DELIVERY").length,
      };

      return {
        totalOrders,
        completedOrders,
        cancelledOrders,
        totalRevenue,
        averageOrderValue: completedOrders > 0 ? totalRevenue / completedOrders : 0,
        byType,
      };
    }),

  // Get today's orders summary
  getTodaySummary: orderViewProcedure
    .input(z.object({ locationId: z.string().uuid().optional() }))
    .query(async ({ ctx, input }) => {
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      const todayISO = today.toISOString();

      let query = ctx.db
        .from("orders")
        .select("status, total")
        .eq("organization_id", ctx.organizationId)
        .gte("created_at", todayISO);

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

      const orders = data ?? [];
      const totalOrders = orders.length;
      const completedOrders = orders.filter((o) => o.status === "COMPLETED").length;
      const openOrders = orders.filter((o) =>
        ["OPEN", "IN_PROGRESS", "READY"].includes(o.status ?? "")
      ).length;
      const revenue = orders
        .filter((o) => o.status === "COMPLETED")
        .reduce((sum, o) => sum + (o.total ?? 0), 0);

      return {
        totalOrders,
        completedOrders,
        openOrders,
        revenue,
      };
    }),
});
