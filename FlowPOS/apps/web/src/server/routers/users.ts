import { router, publicProcedure } from "../trpc";

export const usersRouter = router({
  _health: publicProcedure.query(() => ({ status: "ok" })),
});
