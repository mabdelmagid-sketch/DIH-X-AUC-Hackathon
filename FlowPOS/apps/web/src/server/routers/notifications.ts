import { router, publicProcedure } from "../trpc";

export const notificationsRouter = router({
  _health: publicProcedure.query(() => ({ status: "ok" })),
});
