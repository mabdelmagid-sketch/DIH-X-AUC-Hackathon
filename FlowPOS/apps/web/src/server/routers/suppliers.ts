import { z } from "zod";
import { router, protectedProcedure, adminProcedure } from "../trpc";
import { TRPCError } from "@trpc/server";

// Schema validators
const supplierIdSchema = z.object({
  id: z.string().uuid(),
});

const createSupplierSchema = z.object({
  name: z.string().min(1).max(255),
  contactName: z.string().max(255).optional(),
  email: z.string().email().optional().or(z.literal("")),
  phone: z.string().max(50).optional(),
  address: z.string().max(500).optional(),
  paymentTerms: z.string().max(50).optional(),
  notes: z.string().max(1000).optional(),
  isActive: z.boolean().default(true),
});

const updateSupplierSchema = createSupplierSchema.partial().extend({
  id: z.string().uuid(),
});

const listQuerySchema = z.object({
  search: z.string().optional(),
  isActive: z.boolean().optional(),
  limit: z.number().int().min(1).max(100).default(50),
  offset: z.number().int().min(0).default(0),
});

export const suppliersRouter = router({
  // List all suppliers for the organization
  list: protectedProcedure
    .input(listQuerySchema.optional())
    .query(async ({ ctx, input }) => {
      let query = ctx.db
        .from("suppliers")
        .select("*", { count: "exact" })
        .eq("organization_id", ctx.organizationId)
        .is("deleted_at", null)
        .order("name", { ascending: true });

      if (input?.isActive !== undefined) {
        query = query.eq("is_active", input.isActive);
      }

      if (input?.search) {
        query = query.or(
          `name.ilike.%${input.search}%,contact_name.ilike.%${input.search}%,email.ilike.%${input.search}%`
        );
      }

      if (input?.limit) {
        query = query.limit(input.limit);
      }

      if (input?.offset) {
        query = query.range(input.offset, input.offset + (input?.limit ?? 50) - 1);
      }

      const { data, error, count } = await query;

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return {
        suppliers: data ?? [],
        total: count ?? 0,
      };
    }),

  // Get a single supplier by ID
  get: protectedProcedure
    .input(supplierIdSchema)
    .query(async ({ ctx, input }) => {
      const { data, error } = await ctx.db
        .from("suppliers")
        .select("*")
        .eq("id", input.id)
        .eq("organization_id", ctx.organizationId)
        .is("deleted_at", null)
        .single();

      if (error || !data) {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "Supplier not found",
        });
      }

      return data;
    }),

  // Create a new supplier
  create: adminProcedure
    .input(createSupplierSchema)
    .mutation(async ({ ctx, input }) => {
      const { data, error } = await ctx.db
        .from("suppliers")
        .insert({
          organization_id: ctx.organizationId,
          name: input.name,
          contact_name: input.contactName || null,
          email: input.email || null,
          phone: input.phone || null,
          address: input.address || null,
          payment_terms: input.paymentTerms || null,
          notes: input.notes || null,
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

  // Update an existing supplier
  update: adminProcedure
    .input(updateSupplierSchema)
    .mutation(async ({ ctx, input }) => {
      const { id, ...updateData } = input;

      // Build update object with snake_case keys
      const updatePayload: Record<string, unknown> = {};
      if (updateData.name !== undefined) updatePayload.name = updateData.name;
      if (updateData.contactName !== undefined) updatePayload.contact_name = updateData.contactName;
      if (updateData.email !== undefined) updatePayload.email = updateData.email || null;
      if (updateData.phone !== undefined) updatePayload.phone = updateData.phone;
      if (updateData.address !== undefined) updatePayload.address = updateData.address;
      if (updateData.paymentTerms !== undefined) updatePayload.payment_terms = updateData.paymentTerms;
      if (updateData.notes !== undefined) updatePayload.notes = updateData.notes;
      if (updateData.isActive !== undefined) updatePayload.is_active = updateData.isActive;

      const { data, error } = await ctx.db
        .from("suppliers")
        .update(updatePayload)
        .eq("id", id)
        .eq("organization_id", ctx.organizationId)
        .is("deleted_at", null)
        .select()
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
          message: "Supplier not found",
        });
      }

      return data;
    }),

  // Soft delete a supplier
  delete: adminProcedure
    .input(supplierIdSchema)
    .mutation(async ({ ctx, input }) => {
      // Check if supplier has active ingredients
      const { count: ingredientCount } = await ctx.db
        .from("ingredients")
        .select("id", { count: "exact", head: true })
        .eq("supplier_id", input.id)
        .is("deleted_at", null);

      if (ingredientCount && ingredientCount > 0) {
        throw new TRPCError({
          code: "PRECONDITION_FAILED",
          message: `Cannot delete supplier with ${ingredientCount} active ingredients. Reassign or delete the ingredients first.`,
        });
      }

      const { error } = await ctx.db
        .from("suppliers")
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

  // Get supplier with their ingredients
  getWithIngredients: protectedProcedure
    .input(supplierIdSchema)
    .query(async ({ ctx, input }) => {
      const { data: supplier, error: supplierError } = await ctx.db
        .from("suppliers")
        .select("*")
        .eq("id", input.id)
        .eq("organization_id", ctx.organizationId)
        .is("deleted_at", null)
        .single();

      if (supplierError || !supplier) {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "Supplier not found",
        });
      }

      const { data: ingredients, error: ingredientsError } = await ctx.db
        .from("ingredients")
        .select("*")
        .eq("supplier_id", input.id)
        .is("deleted_at", null)
        .order("name", { ascending: true });

      if (ingredientsError) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: ingredientsError.message,
        });
      }

      return {
        ...supplier,
        ingredients: ingredients ?? [],
      };
    }),

  // Get purchase orders for a supplier
  getPurchaseOrders: protectedProcedure
    .input(
      z.object({
        supplierId: z.string().uuid(),
        status: z.enum(["DRAFT", "PENDING", "APPROVED", "ORDERED", "PARTIALLY_RECEIVED", "RECEIVED", "CANCELLED"]).optional(),
        limit: z.number().int().min(1).max(100).default(20),
      })
    )
    .query(async ({ ctx, input }) => {
      let query = ctx.db
        .from("purchase_orders")
        .select("*, location:locations(name)")
        .eq("supplier_id", input.supplierId)
        .eq("organization_id", ctx.organizationId)
        .order("created_at", { ascending: false })
        .limit(input.limit);

      if (input.status) {
        query = query.eq("status", input.status);
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

  // Create a purchase order
  createPurchaseOrder: protectedProcedure
    .input(
      z.object({
        supplierId: z.string().uuid(),
        locationId: z.string().uuid().optional(),
        notes: z.string().optional(),
        items: z.array(
          z.object({
            ingredientId: z.string().uuid(),
            quantity: z.number().min(0),
            unitCost: z.number().min(0),
            notes: z.string().optional(),
          })
        ),
      })
    )
    .mutation(async ({ ctx, input }) => {
      const totalAmount = input.items.reduce(
        (sum, item) => sum + Math.round(item.quantity * item.unitCost),
        0
      );

      const { data: po, error } = await ctx.db
        .from("purchase_orders")
        .insert({
          organization_id: ctx.organizationId,
          supplier_id: input.supplierId,
          location_id: input.locationId ?? null,
          status: "DRAFT",
          notes: input.notes ?? null,
          total_amount: totalAmount,
        })
        .select()
        .single();

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      // Insert line items
      if (input.items.length > 0) {
        const { error: itemsError } = await ctx.db
          .from("purchase_order_items")
          .insert(
            input.items.map((item) => ({
              purchase_order_id: po.id,
              ingredient_id: item.ingredientId,
              quantity: item.quantity,
              unit_cost: item.unitCost,
              notes: item.notes ?? null,
            }))
          );

        if (itemsError) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: itemsError.message,
          });
        }
      }

      return po;
    }),

  // Update purchase order
  updatePurchaseOrder: protectedProcedure
    .input(
      z.object({
        id: z.string().uuid(),
        notes: z.string().optional(),
        items: z
          .array(
            z.object({
              ingredientId: z.string().uuid(),
              quantity: z.number().min(0),
              unitCost: z.number().min(0),
              notes: z.string().optional(),
            })
          )
          .optional(),
      })
    )
    .mutation(async ({ ctx, input }) => {
      const payload: Record<string, unknown> = { updated_at: new Date().toISOString() };
      if (input.notes !== undefined) payload.notes = input.notes;

      if (input.items) {
        payload.total_amount = input.items.reduce(
          (sum, item) => sum + Math.round(item.quantity * item.unitCost),
          0
        );
      }

      const { data, error } = await ctx.db
        .from("purchase_orders")
        .update(payload)
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

      // Replace items if provided
      if (input.items) {
        await ctx.db
          .from("purchase_order_items")
          .delete()
          .eq("purchase_order_id", input.id);

        if (input.items.length > 0) {
          await ctx.db.from("purchase_order_items").insert(
            input.items.map((item) => ({
              purchase_order_id: input.id,
              ingredient_id: item.ingredientId,
              quantity: item.quantity,
              unit_cost: item.unitCost,
              notes: item.notes ?? null,
            }))
          );
        }
      }

      return data;
    }),

  // Update purchase order status
  updatePurchaseOrderStatus: protectedProcedure
    .input(
      z.object({
        id: z.string().uuid(),
        status: z.enum(["DRAFT", "PENDING", "APPROVED", "ORDERED", "PARTIALLY_RECEIVED", "RECEIVED", "CANCELLED"]),
      })
    )
    .mutation(async ({ ctx, input }) => {
      const payload: Record<string, unknown> = {
        status: input.status,
        updated_at: new Date().toISOString(),
      };

      if (input.status === "ORDERED") {
        payload.order_date = new Date().toISOString();
      }
      if (input.status === "RECEIVED") {
        payload.received_date = new Date().toISOString();
      }

      const { data, error } = await ctx.db
        .from("purchase_orders")
        .update(payload)
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

  // Receive a purchase order - triggers add_ingredient_batch_atomic for each line item
  receivePurchaseOrder: protectedProcedure
    .input(
      z.object({
        id: z.string().uuid(),
        locationId: z.string().uuid(),
        items: z.array(
          z.object({
            purchaseOrderItemId: z.string().uuid(),
            ingredientId: z.string().uuid(),
            receivedQty: z.number().min(0),
            unitCost: z.number().min(0),
            batchNumber: z.string().optional(),
            expiryDate: z.string().optional(),
          })
        ),
      })
    )
    .mutation(async ({ ctx, input }) => {
      // Process each line item as a new batch
      for (const item of input.items) {
        if (item.receivedQty <= 0) continue;

        // Create batch atomically
        await (ctx.db.rpc as CallableFunction)("add_ingredient_batch_atomic", {
          p_ingredient_id: item.ingredientId,
          p_location_id: input.locationId,
          p_quantity: item.receivedQty,
          p_batch_number: item.batchNumber ?? null,
          p_cost_per_unit: item.unitCost,
          p_expiry_date: item.expiryDate ?? null,
          p_supplier_id: null, // Already tracked via PO
          p_purchase_order_id: input.id,
          p_notes: null,
          p_user_id: ctx.user.id,
          p_organization_id: ctx.organizationId,
        });

        // Update received qty on the PO item
        await ctx.db
          .from("purchase_order_items")
          .update({ received_qty: item.receivedQty })
          .eq("id", item.purchaseOrderItemId);
      }

      // Check if all items fully received
      const { data: poItems } = await ctx.db
        .from("purchase_order_items")
        .select("quantity, received_qty")
        .eq("purchase_order_id", input.id);

      const allReceived = (poItems ?? []).every(
        (item) => (item.received_qty ?? 0) >= item.quantity
      );

      // Update PO status
      await ctx.db
        .from("purchase_orders")
        .update({
          status: allReceived ? "RECEIVED" : "PARTIALLY_RECEIVED",
          received_date: allReceived ? new Date().toISOString() : null,
          updated_at: new Date().toISOString(),
        })
        .eq("id", input.id);

      return { success: true, fullyReceived: allReceived };
    }),

  // Delete a purchase order (only DRAFT status)
  deletePurchaseOrder: protectedProcedure
    .input(z.object({ id: z.string().uuid() }))
    .mutation(async ({ ctx, input }) => {
      const { error } = await ctx.db
        .from("purchase_orders")
        .delete()
        .eq("id", input.id)
        .eq("organization_id", ctx.organizationId)
        .eq("status", "DRAFT");

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return { success: true };
    }),
});
