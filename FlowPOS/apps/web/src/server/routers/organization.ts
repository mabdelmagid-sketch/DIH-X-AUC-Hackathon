import { z } from "zod";
import {
  router,
  settingsViewProcedure,
  settingsEditProcedure,
} from "../trpc";
import { TRPCError } from "@trpc/server";

const settingsUpdateSchema = z.object({
  currency: z.string().max(10).optional(),
  timezone: z.string().max(100).optional(),
  taxRate: z.number().int().min(0).max(10000).optional(), // stored as basis points (1000 = 10%)
  taxInclusive: z.boolean().optional(),
  receiptHeader: z.string().max(500).optional().nullable(),
  receiptFooter: z.string().max(500).optional().nullable(),
  showLogo: z.boolean().optional(),
  requirePin: z.boolean().optional(),
  allowNegative: z.boolean().optional(),
});

const orgUpdateSchema = z.object({
  name: z.string().min(1).max(255).optional(),
});

export const organizationRouter = router({
  // Get organization info
  get: settingsViewProcedure.query(async ({ ctx }) => {
    const { data, error } = await ctx.db
      .from("organizations")
      .select("*")
      .eq("id", ctx.organizationId)
      .single();

    if (error) {
      throw new TRPCError({
        code: "INTERNAL_SERVER_ERROR",
        message: error.message,
      });
    }

    return data;
  }),

  // Update organization name
  update: settingsEditProcedure
    .input(orgUpdateSchema)
    .mutation(async ({ ctx, input }) => {
      const updatePayload: Record<string, unknown> = {
        updated_at: new Date().toISOString(),
      };
      if (input.name !== undefined) updatePayload.name = input.name;

      const { data, error } = await ctx.db
        .from("organizations")
        .update(updatePayload)
        .eq("id", ctx.organizationId)
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

  // Get settings for the organization
  getSettings: settingsViewProcedure.query(async ({ ctx }) => {
    const { data, error } = await ctx.db
      .from("organization_settings")
      .select("*")
      .eq("organization_id", ctx.organizationId)
      .single();

    if (error) {
      // If no settings row exists yet, return defaults
      if (error.code === "PGRST116") {
        return {
          id: null,
          organization_id: ctx.organizationId,
          currency: "USD",
          timezone: "America/New_York",
          tax_rate: 0,
          tax_inclusive: false,
          receipt_header: null,
          receipt_footer: null,
          show_logo: true,
          require_pin: false,
          allow_negative: false,
          default_tip_percentages: [15, 18, 20, 25],
          pos_name: "Banger POS",
          pos_logo: null,
          plan: "free",
          ai_credits_used: 0,
          ai_credits_limit: 0,
        };
      }

      throw new TRPCError({
        code: "INTERNAL_SERVER_ERROR",
        message: error.message,
      });
    }

    return data;
  }),

  // Update settings
  updateSettings: settingsEditProcedure
    .input(settingsUpdateSchema)
    .mutation(async ({ ctx, input }) => {
      const updatePayload: Record<string, unknown> = {};
      if (input.currency !== undefined) updatePayload.currency = input.currency;
      if (input.timezone !== undefined) updatePayload.timezone = input.timezone;
      if (input.taxRate !== undefined) updatePayload.tax_rate = input.taxRate;
      if (input.taxInclusive !== undefined) updatePayload.tax_inclusive = input.taxInclusive;
      if (input.receiptHeader !== undefined) updatePayload.receipt_header = input.receiptHeader;
      if (input.receiptFooter !== undefined) updatePayload.receipt_footer = input.receiptFooter;
      if (input.showLogo !== undefined) updatePayload.show_logo = input.showLogo;
      if (input.requirePin !== undefined) updatePayload.require_pin = input.requirePin;
      if (input.allowNegative !== undefined) updatePayload.allow_negative = input.allowNegative;

      // Try update first
      const { data, error } = await ctx.db
        .from("organization_settings")
        .update(updatePayload)
        .eq("organization_id", ctx.organizationId)
        .select()
        .single();

      if (error) {
        // If no row exists, create one
        if (error.code === "PGRST116") {
          const { data: inserted, error: insertError } = await ctx.db
            .from("organization_settings")
            .insert({
              organization_id: ctx.organizationId,
              ...updatePayload,
            })
            .select()
            .single();

          if (insertError) {
            throw new TRPCError({
              code: "INTERNAL_SERVER_ERROR",
              message: insertError.message,
            });
          }

          return inserted;
        }

        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return data;
    }),
});
