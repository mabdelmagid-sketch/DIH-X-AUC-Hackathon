import { router, publicProcedure } from "../trpc";

export const insightsRouter = router({
  _health: publicProcedure.query(() => ({ status: "ok" })),
});
