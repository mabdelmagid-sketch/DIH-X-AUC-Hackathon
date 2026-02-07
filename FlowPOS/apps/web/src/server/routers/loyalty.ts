import { z } from "zod";
import { router, protectedProcedure, adminProcedure } from "../trpc";
import { TRPCError } from "@trpc/server";

// Schemas
const tierSchema = z.object({
  name: z.string().min(1).max(100),
  minPoints: z.number().int().min(0),
  pointsMultiplier: z.number().min(1).default(1),
  perks: z.array(z.string()).default([]),
  color: z.string().max(20).optional(),
  sortOrder: z.number().int().default(0),
});

const rewardSchema = z.object({
  name: z.string().min(1).max(255),
  description: z.string().max(500).optional(),
  pointsCost: z.number().int().min(0),
  type: z.enum(["discount_percentage", "discount_fixed", "free_item", "store_credit", "punch_card"]),
  value: z.number().min(0).default(0),
  isActive: z.boolean().default(true),
  buyQuantity: z.number().int().optional(),
  freeQuantity: z.number().int().optional(),
  categoryId: z.string().uuid().optional(),
  productId: z.string().uuid().optional(),
  spendAmount: z.number().int().optional(),
  discountType: z.string().optional(),
});

const memberSchema = z.object({
  customerId: z.string().uuid().optional(),
  customerName: z.string().min(1),
  customerEmail: z.string().email().optional(),
  customerPhone: z.string().optional(),
  birthday: z.string().optional(),
  anniversary: z.string().optional(),
  tags: z.array(z.string()).default([]),
});

export const loyaltyRouter = router({
  // ==================== TIERS ====================
  listTiers: protectedProcedure.query(async ({ ctx }) => {
    const { data, error } = await ctx.db
      .from("loyalty_tiers")
      .select("*")
      .eq("organization_id", ctx.organizationId)
      .order("sort_order", { ascending: true });

    if (error) {
      throw new TRPCError({ code: "INTERNAL_SERVER_ERROR", message: error.message });
    }
    return data ?? [];
  }),

  createTier: adminProcedure.input(tierSchema).mutation(async ({ ctx, input }) => {
    const { data, error } = await ctx.db
      .from("loyalty_tiers")
      .insert({
        organization_id: ctx.organizationId,
        name: input.name,
        min_points: input.minPoints,
        points_multiplier: input.pointsMultiplier,
        perks: input.perks,
        color: input.color ?? null,
        sort_order: input.sortOrder,
      })
      .select()
      .single();

    if (error) {
      throw new TRPCError({ code: "INTERNAL_SERVER_ERROR", message: error.message });
    }
    return data;
  }),

  updateTier: adminProcedure
    .input(tierSchema.partial().extend({ id: z.string().uuid() }))
    .mutation(async ({ ctx, input }) => {
      const { id, ...updateData } = input;
      const payload: Record<string, unknown> = {};
      if (updateData.name !== undefined) payload.name = updateData.name;
      if (updateData.minPoints !== undefined) payload.min_points = updateData.minPoints;
      if (updateData.pointsMultiplier !== undefined) payload.points_multiplier = updateData.pointsMultiplier;
      if (updateData.perks !== undefined) payload.perks = updateData.perks;
      if (updateData.color !== undefined) payload.color = updateData.color;
      if (updateData.sortOrder !== undefined) payload.sort_order = updateData.sortOrder;
      payload.updated_at = new Date().toISOString();

      const { data, error } = await ctx.db
        .from("loyalty_tiers")
        .update(payload)
        .eq("id", id)
        .eq("organization_id", ctx.organizationId)
        .select()
        .single();

      if (error) {
        throw new TRPCError({ code: "INTERNAL_SERVER_ERROR", message: error.message });
      }
      return data;
    }),

  deleteTier: adminProcedure
    .input(z.object({ id: z.string().uuid() }))
    .mutation(async ({ ctx, input }) => {
      const { error } = await ctx.db
        .from("loyalty_tiers")
        .delete()
        .eq("id", input.id)
        .eq("organization_id", ctx.organizationId);

      if (error) {
        throw new TRPCError({ code: "INTERNAL_SERVER_ERROR", message: error.message });
      }
      return { success: true };
    }),

  // ==================== REWARDS ====================
  listRewards: protectedProcedure.query(async ({ ctx }) => {
    const { data, error } = await ctx.db
      .from("loyalty_rewards")
      .select("*")
      .eq("organization_id", ctx.organizationId)
      .order("points_cost", { ascending: true });

    if (error) {
      throw new TRPCError({ code: "INTERNAL_SERVER_ERROR", message: error.message });
    }
    return data ?? [];
  }),

  createReward: adminProcedure.input(rewardSchema).mutation(async ({ ctx, input }) => {
    const { data, error } = await ctx.db
      .from("loyalty_rewards")
      .insert({
        organization_id: ctx.organizationId,
        name: input.name,
        description: input.description ?? null,
        points_cost: input.pointsCost,
        type: input.type,
        value: input.value,
        is_active: input.isActive,
        buy_quantity: input.buyQuantity ?? null,
        free_quantity: input.freeQuantity ?? null,
        category_id: input.categoryId ?? null,
        product_id: input.productId ?? null,
        spend_amount: input.spendAmount ?? null,
        discount_type: input.discountType ?? null,
      })
      .select()
      .single();

    if (error) {
      throw new TRPCError({ code: "INTERNAL_SERVER_ERROR", message: error.message });
    }
    return data;
  }),

  updateReward: adminProcedure
    .input(rewardSchema.partial().extend({ id: z.string().uuid() }))
    .mutation(async ({ ctx, input }) => {
      const { id, ...updateData } = input;
      const payload: Record<string, unknown> = {};
      if (updateData.name !== undefined) payload.name = updateData.name;
      if (updateData.description !== undefined) payload.description = updateData.description;
      if (updateData.pointsCost !== undefined) payload.points_cost = updateData.pointsCost;
      if (updateData.type !== undefined) payload.type = updateData.type;
      if (updateData.value !== undefined) payload.value = updateData.value;
      if (updateData.isActive !== undefined) payload.is_active = updateData.isActive;
      if (updateData.buyQuantity !== undefined) payload.buy_quantity = updateData.buyQuantity;
      if (updateData.freeQuantity !== undefined) payload.free_quantity = updateData.freeQuantity;
      if (updateData.categoryId !== undefined) payload.category_id = updateData.categoryId;
      if (updateData.productId !== undefined) payload.product_id = updateData.productId;
      payload.updated_at = new Date().toISOString();

      const { data, error } = await ctx.db
        .from("loyalty_rewards")
        .update(payload)
        .eq("id", id)
        .eq("organization_id", ctx.organizationId)
        .select()
        .single();

      if (error) {
        throw new TRPCError({ code: "INTERNAL_SERVER_ERROR", message: error.message });
      }
      return data;
    }),

  deleteReward: adminProcedure
    .input(z.object({ id: z.string().uuid() }))
    .mutation(async ({ ctx, input }) => {
      const { error } = await ctx.db
        .from("loyalty_rewards")
        .delete()
        .eq("id", input.id)
        .eq("organization_id", ctx.organizationId);

      if (error) {
        throw new TRPCError({ code: "INTERNAL_SERVER_ERROR", message: error.message });
      }
      return { success: true };
    }),

  // ==================== MEMBERS ====================
  listMembers: protectedProcedure
    .input(
      z.object({
        search: z.string().optional(),
        tierId: z.string().uuid().optional(),
        tag: z.string().optional(),
        limit: z.number().int().min(1).max(100).default(50),
        offset: z.number().int().min(0).default(0),
      }).optional()
    )
    .query(async ({ ctx, input }) => {
      let query = ctx.db
        .from("loyalty_members")
        .select("*, tier:loyalty_tiers(id, name, color)", { count: "exact" })
        .eq("organization_id", ctx.organizationId)
        .order("last_activity", { ascending: false, nullsFirst: false });

      if (input?.search) {
        query = query.or(
          `customer_name.ilike.%${input.search}%,customer_email.ilike.%${input.search}%,customer_phone.ilike.%${input.search}%`
        );
      }

      if (input?.tierId) {
        query = query.eq("tier_id", input.tierId);
      }

      if (input?.tag) {
        query = query.contains("tags", [input.tag]);
      }

      const { data, error, count } = await query.range(
        input?.offset ?? 0,
        (input?.offset ?? 0) + (input?.limit ?? 50) - 1
      );

      if (error) {
        throw new TRPCError({ code: "INTERNAL_SERVER_ERROR", message: error.message });
      }
      return { members: data ?? [], total: count ?? 0 };
    }),

  getMember: protectedProcedure
    .input(z.object({ id: z.string().uuid() }))
    .query(async ({ ctx, input }) => {
      const { data, error } = await ctx.db
        .from("loyalty_members")
        .select("*, tier:loyalty_tiers(*)")
        .eq("id", input.id)
        .eq("organization_id", ctx.organizationId)
        .single();

      if (error) {
        throw new TRPCError({ code: "NOT_FOUND", message: "Member not found" });
      }
      return data;
    }),

  getMemberByCustomerId: protectedProcedure
    .input(z.object({ customerId: z.string().uuid() }))
    .query(async ({ ctx, input }) => {
      const { data } = await ctx.db
        .from("loyalty_members")
        .select("*, tier:loyalty_tiers(*)")
        .eq("customer_id", input.customerId)
        .eq("organization_id", ctx.organizationId)
        .single();

      return data ?? null;
    }),

  addMember: protectedProcedure.input(memberSchema).mutation(async ({ ctx, input }) => {
    const { data, error } = await ctx.db
      .from("loyalty_members")
      .insert({
        organization_id: ctx.organizationId,
        customer_id: input.customerId ?? null,
        customer_name: input.customerName,
        customer_email: input.customerEmail ?? null,
        customer_phone: input.customerPhone ?? null,
        birthday: input.birthday ?? null,
        anniversary: input.anniversary ?? null,
        tags: input.tags,
        joined_at: new Date().toISOString(),
      })
      .select()
      .single();

    if (error) {
      throw new TRPCError({ code: "INTERNAL_SERVER_ERROR", message: error.message });
    }
    return data;
  }),

  // ==================== POINTS ====================
  earnPoints: protectedProcedure
    .input(
      z.object({
        memberId: z.string().uuid(),
        points: z.number().int().min(1),
        description: z.string().default("Points earned"),
        orderId: z.string().uuid().optional(),
      })
    )
    .mutation(async ({ ctx, input }) => {
      // Get member with tier for multiplier
      const { data: member } = await ctx.db
        .from("loyalty_members")
        .select("id, points, total_points_earned, tier:loyalty_tiers(points_multiplier)")
        .eq("id", input.memberId)
        .eq("organization_id", ctx.organizationId)
        .single();

      if (!member) {
        throw new TRPCError({ code: "NOT_FOUND", message: "Member not found" });
      }

      const tier = member.tier as { points_multiplier: number } | null;
      const multiplier = tier?.points_multiplier ?? 1;
      const adjustedPoints = Math.floor(input.points * multiplier);

      // Update member points
      await ctx.db
        .from("loyalty_members")
        .update({
          points: (member.points ?? 0) + adjustedPoints,
          total_points_earned: (member.total_points_earned ?? 0) + adjustedPoints,
          last_activity: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        })
        .eq("id", input.memberId);

      // Record transaction
      await ctx.db.from("point_transactions").insert({
        organization_id: ctx.organizationId,
        member_id: input.memberId,
        type: "earn",
        points: adjustedPoints,
        description: input.description,
        order_id: input.orderId ?? null,
      });

      return { pointsEarned: adjustedPoints };
    }),

  redeemPoints: protectedProcedure
    .input(
      z.object({
        memberId: z.string().uuid(),
        points: z.number().int().min(1),
        description: z.string().default("Points redeemed"),
        orderId: z.string().uuid().optional(),
      })
    )
    .mutation(async ({ ctx, input }) => {
      const { data: member } = await ctx.db
        .from("loyalty_members")
        .select("id, points, total_points_redeemed")
        .eq("id", input.memberId)
        .eq("organization_id", ctx.organizationId)
        .single();

      if (!member) {
        throw new TRPCError({ code: "NOT_FOUND", message: "Member not found" });
      }

      if ((member.points ?? 0) < input.points) {
        throw new TRPCError({ code: "BAD_REQUEST", message: "Insufficient points" });
      }

      await ctx.db
        .from("loyalty_members")
        .update({
          points: (member.points ?? 0) - input.points,
          total_points_redeemed: (member.total_points_redeemed ?? 0) + input.points,
          last_activity: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        })
        .eq("id", input.memberId);

      await ctx.db.from("point_transactions").insert({
        organization_id: ctx.organizationId,
        member_id: input.memberId,
        type: "redeem",
        points: -input.points,
        description: input.description,
        order_id: input.orderId ?? null,
      });

      return { pointsRedeemed: input.points };
    }),

  getPointHistory: protectedProcedure
    .input(
      z.object({
        memberId: z.string().uuid(),
        limit: z.number().int().min(1).max(100).default(50),
        offset: z.number().int().min(0).default(0),
      })
    )
    .query(async ({ ctx, input }) => {
      const { data, error, count } = await ctx.db
        .from("point_transactions")
        .select("*", { count: "exact" })
        .eq("member_id", input.memberId)
        .eq("organization_id", ctx.organizationId)
        .order("created_at", { ascending: false })
        .range(input.offset, input.offset + input.limit - 1);

      if (error) {
        throw new TRPCError({ code: "INTERNAL_SERVER_ERROR", message: error.message });
      }
      return { transactions: data ?? [], total: count ?? 0 };
    }),

  // ==================== STORE CREDIT ====================
  issueStoreCredit: protectedProcedure
    .input(
      z.object({
        memberId: z.string().uuid(),
        amount: z.number().int().min(1),
        description: z.string().default("Store credit issued"),
        expiresAt: z.string().optional(),
      })
    )
    .mutation(async ({ ctx, input }) => {
      const { data: member } = await ctx.db
        .from("loyalty_members")
        .select("id, store_credit, total_credit_issued")
        .eq("id", input.memberId)
        .eq("organization_id", ctx.organizationId)
        .single();

      if (!member) {
        throw new TRPCError({ code: "NOT_FOUND", message: "Member not found" });
      }

      const newBalance = (member.store_credit ?? 0) + input.amount;

      await ctx.db
        .from("loyalty_members")
        .update({
          store_credit: newBalance,
          total_credit_issued: (member.total_credit_issued ?? 0) + input.amount,
          updated_at: new Date().toISOString(),
        })
        .eq("id", input.memberId);

      await ctx.db.from("store_credit_transactions").insert({
        organization_id: ctx.organizationId,
        member_id: input.memberId,
        type: "issue",
        amount: input.amount,
        balance: newBalance,
        description: input.description,
        issued_by: ctx.user.id,
        expires_at: input.expiresAt ?? null,
      });

      return { newBalance };
    }),

  useStoreCredit: protectedProcedure
    .input(
      z.object({
        memberId: z.string().uuid(),
        amount: z.number().int().min(1),
        description: z.string().default("Store credit used"),
        orderId: z.string().uuid().optional(),
      })
    )
    .mutation(async ({ ctx, input }) => {
      const { data: member } = await ctx.db
        .from("loyalty_members")
        .select("id, store_credit, total_credit_used")
        .eq("id", input.memberId)
        .eq("organization_id", ctx.organizationId)
        .single();

      if (!member) {
        throw new TRPCError({ code: "NOT_FOUND", message: "Member not found" });
      }

      if ((member.store_credit ?? 0) < input.amount) {
        throw new TRPCError({ code: "BAD_REQUEST", message: "Insufficient store credit" });
      }

      const newBalance = (member.store_credit ?? 0) - input.amount;

      await ctx.db
        .from("loyalty_members")
        .update({
          store_credit: newBalance,
          total_credit_used: (member.total_credit_used ?? 0) + input.amount,
          updated_at: new Date().toISOString(),
        })
        .eq("id", input.memberId);

      await ctx.db.from("store_credit_transactions").insert({
        organization_id: ctx.organizationId,
        member_id: input.memberId,
        type: "use",
        amount: -input.amount,
        balance: newBalance,
        description: input.description,
        order_id: input.orderId ?? null,
      });

      return { newBalance };
    }),
});
