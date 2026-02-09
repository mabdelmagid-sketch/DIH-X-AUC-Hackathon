import { router, publicProcedure } from "../trpc";

export const cashDrawerRouter = router({
  _health: publicProcedure.query(() => ({ status: "ok" })),
});
