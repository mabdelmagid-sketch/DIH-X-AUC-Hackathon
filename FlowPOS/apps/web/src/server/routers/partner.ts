import { router, publicProcedure } from "../trpc";

export const partnerRouter = router({
  _health: publicProcedure.query(() => ({ status: "ok" })),
});
