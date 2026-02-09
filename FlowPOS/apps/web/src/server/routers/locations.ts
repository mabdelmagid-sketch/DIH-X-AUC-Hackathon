import { router, protectedProcedure } from "../trpc";
import { TRPCError } from "@trpc/server";

export const locationsRouter = router({
  list: protectedProcedure.query(async ({ ctx }) => {
    const { data, error } = await ctx.db
      .from("locations")
      .select("id, name, address, phone, is_active")
      .eq("organization_id", ctx.organizationId)
      .order("name", { ascending: true });

    if (error) {
      throw new TRPCError({
        code: "INTERNAL_SERVER_ERROR",
        message: error.message,
      });
    }

    return data ?? [];
  }),
});
