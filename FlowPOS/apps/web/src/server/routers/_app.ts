import { router } from "../trpc";
import { authRouter } from "./auth";
import { productsRouter } from "./products";
import { categoriesRouter } from "./categories";
import { customersRouter } from "./customers";
import { ordersRouter } from "./orders";
import { employeesRouter } from "./employees";
import { inventoryRouter } from "./inventory";
import { tablesRouter } from "./tables";
import { organizationRouter } from "./organization";
import { locationsRouter } from "./locations";
import { notificationsRouter } from "./notifications";
import { usersRouter } from "./users";
import { cashDrawerRouter } from "./cash-drawer";
import { platformAdminRouter } from "./platform-admin";
import { partnerRouter } from "./partner";
import { suppliersRouter } from "./suppliers";
import { ingredientsRouter } from "./ingredients";
import { recipesRouter } from "./recipes";
import { insightsRouter } from "./insights";
import { couponsRouter } from "./coupons";
import { loyaltyRouter } from "./loyalty";

/**
 * Root router for the application
 * Contains all sub-routers for different entities
 */
export const appRouter = router({
  auth: authRouter,
  products: productsRouter,
  categories: categoriesRouter,
  customers: customersRouter,
  orders: ordersRouter,
  employees: employeesRouter,
  inventory: inventoryRouter,
  tables: tablesRouter,
  organization: organizationRouter,
  locations: locationsRouter,
  notifications: notificationsRouter,
  users: usersRouter,
  cashDrawer: cashDrawerRouter,
  platformAdmin: platformAdminRouter,
  partner: partnerRouter,
  suppliers: suppliersRouter,
  ingredients: ingredientsRouter,
  recipes: recipesRouter,
  insights: insightsRouter,
  coupons: couponsRouter,
  loyalty: loyaltyRouter,
});

// Export type definition of API
export type AppRouter = typeof appRouter;
