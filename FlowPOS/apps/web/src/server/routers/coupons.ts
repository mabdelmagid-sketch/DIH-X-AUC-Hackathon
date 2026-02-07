import { z } from "zod";
import { router, protectedProcedure, adminProcedure } from "../trpc";
import { TRPCError } from "@trpc/server";

const couponTypeEnum = z.enum(["percentage", "fixed", "bogo", "free_item"]);

const couponIdSchema = z.object({
  id: z.string().uuid(),
});

const createCouponSchema = z.object({
  code: z.string().min(1).max(50),
  name: z.string().min(1).max(255),
  type: couponTypeEnum,
  value: z.number().int().min(0),
  minOrderAmount: z.number().int().min(0).optional(),
  maxUses: z.number().int().min(1).optional(),
  validFrom: z.string(), // ISO date
  validUntil: z.string(), // ISO date
  isActive: z.boolean().default(true),
  applicableProducts: z.array(z.string().uuid()).default([]),
  applicableCategories: z.array(z.string().uuid()).default([]),
});

const updateCouponSchema = createCouponSchema.partial().extend({
  id: z.string().uuid(),
});

export const couponsRouter = router({
  // List all coupons for the organization
  list: protectedProcedure
    .input(
      z.object({
        search: z.string().optional(),
        isActive: z.boolean().optional(),
        limit: z.number().int().min(1).max(100).default(50),
        offset: z.number().int().min(0).default(0),
      }).optional()
    )
    .query(async ({ ctx, input }) => {
      let query = ctx.db
        .from("coupons")
        .select("*", { count: "exact" })
        .eq("organization_id", ctx.organizationId)
        .order("created_at", { ascending: false });

      if (input?.isActive !== undefined) {
        query = query.eq("is_active", input.isActive);
      }

      if (input?.search) {
        query = query.or(
          `code.ilike.%${input.search}%,name.ilike.%${input.search}%`
        );
      }

      const { data, error, count } = await query.range(
        input?.offset ?? 0,
        (input?.offset ?? 0) + (input?.limit ?? 50) - 1
      );

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return { coupons: data ?? [], total: count ?? 0 };
    }),

  // Get a single coupon
  get: protectedProcedure
    .input(couponIdSchema)
    .query(async ({ ctx, input }) => {
      const { data, error } = await ctx.db
        .from("coupons")
        .select("*")
        .eq("id", input.id)
        .eq("organization_id", ctx.organizationId)
        .single();

      if (error) {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "Coupon not found",
        });
      }

      return data;
    }),

  // Create a coupon
  create: adminProcedure
    .input(createCouponSchema)
    .mutation(async ({ ctx, input }) => {
      const { data, error } = await ctx.db
        .from("coupons")
        .insert({
          organization_id: ctx.organizationId,
          code: input.code.toUpperCase(),
          name: input.name,
          type: input.type,
          value: input.value,
          min_order_amount: input.minOrderAmount ?? null,
          max_uses: input.maxUses ?? null,
          valid_from: input.validFrom,
          valid_until: input.validUntil,
          is_active: input.isActive,
          applicable_products: input.applicableProducts,
          applicable_categories: input.applicableCategories,
        })
        .select()
        .single();

      if (error) {
        if (error.code === "23505") {
          throw new TRPCError({
            code: "CONFLICT",
            message: "A coupon with this code already exists",
          });
        }
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return data;
    }),

  // Update a coupon
  update: adminProcedure
    .input(updateCouponSchema)
    .mutation(async ({ ctx, input }) => {
      const { id, ...updateData } = input;
      const payload: Record<string, unknown> = {};

      if (updateData.code !== undefined) payload.code = updateData.code.toUpperCase();
      if (updateData.name !== undefined) payload.name = updateData.name;
      if (updateData.type !== undefined) payload.type = updateData.type;
      if (updateData.value !== undefined) payload.value = updateData.value;
      if (updateData.minOrderAmount !== undefined) payload.min_order_amount = updateData.minOrderAmount;
      if (updateData.maxUses !== undefined) payload.max_uses = updateData.maxUses;
      if (updateData.validFrom !== undefined) payload.valid_from = updateData.validFrom;
      if (updateData.validUntil !== undefined) payload.valid_until = updateData.validUntil;
      if (updateData.isActive !== undefined) payload.is_active = updateData.isActive;
      if (updateData.applicableProducts !== undefined) payload.applicable_products = updateData.applicableProducts;
      if (updateData.applicableCategories !== undefined) payload.applicable_categories = updateData.applicableCategories;

      payload.updated_at = new Date().toISOString();

      const { data, error } = await ctx.db
        .from("coupons")
        .update(payload)
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

  // Delete a coupon
  delete: adminProcedure
    .input(couponIdSchema)
    .mutation(async ({ ctx, input }) => {
      const { error } = await ctx.db
        .from("coupons")
        .delete()
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

  // Validate a coupon code
  validate: protectedProcedure
    .input(
      z.object({
        code: z.string(),
        orderTotal: z.number().int().min(0),
        productIds: z.array(z.string().uuid()).default([]),
        categoryIds: z.array(z.string().uuid()).default([]),
      })
    )
    .query(async ({ ctx, input }) => {
      const { data: coupon, error } = await ctx.db
        .from("coupons")
        .select("*")
        .eq("organization_id", ctx.organizationId)
        .ilike("code", input.code)
        .single();

      if (error || !coupon) {
        return { valid: false, error: "Coupon not found" };
      }

      if (!coupon.is_active) {
        return { valid: false, error: "Coupon is inactive" };
      }

      const now = new Date();
      if (new Date(coupon.valid_from) > now) {
        return { valid: false, error: "Coupon is not yet valid" };
      }
      if (new Date(coupon.valid_until) < now) {
        return { valid: false, error: "Coupon has expired" };
      }

      if (coupon.max_uses && coupon.used_count >= coupon.max_uses) {
        return { valid: false, error: "Coupon usage limit reached" };
      }

      if (coupon.min_order_amount && input.orderTotal < coupon.min_order_amount) {
        return { valid: false, error: `Minimum order amount: ${coupon.min_order_amount}` };
      }

      // Check product/category restrictions
      if (coupon.applicable_products?.length > 0) {
        const hasMatch = input.productIds.some((id) =>
          coupon.applicable_products.includes(id)
        );
        if (!hasMatch) {
          return { valid: false, error: "Coupon not valid for these products" };
        }
      }

      if (coupon.applicable_categories?.length > 0) {
        const hasMatch = input.categoryIds.some((id) =>
          coupon.applicable_categories.includes(id)
        );
        if (!hasMatch) {
          return { valid: false, error: "Coupon not valid for these categories" };
        }
      }

      return { valid: true, coupon };
    }),

  // Apply a coupon (increment usage count)
  applyCoupon: protectedProcedure
    .input(z.object({ code: z.string() }))
    .mutation(async ({ ctx, input }) => {
      const { error } = await ctx.db.rpc("increment_coupon_usage" as string, {
        p_code: input.code.toUpperCase(),
        p_organization_id: ctx.organizationId,
      });

      // Fallback: if the RPC doesn't exist, do it manually
      if (error) {
        const { data: coupon } = await ctx.db
          .from("coupons")
          .select("id, used_count")
          .eq("organization_id", ctx.organizationId)
          .ilike("code", input.code)
          .single();

        if (coupon) {
          await ctx.db
            .from("coupons")
            .update({ used_count: (coupon.used_count ?? 0) + 1 })
            .eq("id", coupon.id);
        }
      }

      return { success: true };
    }),
});
