# Banger POS - Project Memory

## Project Overview
Building a full-featured, AI-powered POS system for restaurants, coffee shops, cinemas, and entertainment venues.

## Tech Stack
- **Frontend**: Next.js 15, React 19, TypeScript, Tailwind CSS v4, shadcn/ui, Zustand (21 stores)
- **Backend**: tRPC v11 with 15 routers, 43 endpoints
- **Database**: Supabase (PostgreSQL) with 25+ models, RLS, generated types
- **Auth**: Supabase Auth + Custom role-based system (Owner, Admin, Manager, Cashier, Kitchen, Waiter)
- **Real-time**: Supabase Realtime (orders, tables)
- **Email**: Resend (receipts, stock alerts)
- **Monitoring**: Sentry (error tracking)
- **PWA**: next-pwa with IndexedDB offline support
- **Mobile**: Capacitor (planned)
- **AI**: Claude/OpenAI API (planned)

## Key Decisions
- Build from scratch (not forking existing solutions)
- Cloud SaaS only (no self-hosted option)
- Single brand (not white-label)
- Restaurant/Cafe MVP first, then expand to other industries
- NO payment gateway integration - users handle payments externally via CliQ
- Simple, clean branding with light/dark theme support

## Project Structure
```
POS/
├── apps/web/              # Next.js main app (33 pages)
│   ├── src/
│   │   ├── app/           # Pages (App Router)
│   │   │   ├── pos/       # POS Terminal
│   │   │   ├── kitchen/   # Kitchen Display
│   │   │   ├── dashboard/ # 13 dashboard pages
│   │   │   ├── admin/     # 4 platform admin pages
│   │   │   ├── (auth)/    # Login & PIN pages
│   │   │   └── api/trpc/  # tRPC API endpoint
│   │   ├── components/    # React components (9 directories)
│   │   ├── server/        # tRPC routers and context
│   │   │   ├── trpc.ts    # tRPC init and procedures
│   │   │   ├── db.ts      # Supabase server client
│   │   │   └── routers/   # 15 entity routers
│   │   ├── store/         # 21 Zustand stores
│   │   ├── hooks/         # Custom hooks (realtime, offline)
│   │   ├── providers/     # Context providers
│   │   ├── i18n/          # Translations (en, ar)
│   │   └── lib/           # Utils, permissions, tRPC client
│   ├── __tests__/         # 324 unit tests
│   └── e2e/               # 5 Playwright E2E test suites
├── packages/db/           # Supabase types + Prisma schema
├── packages/ui/           # Shared UI components
└── BANGER-POS-PLAN.md     # Full feature plan
```

## Current Progress (Production-Ready MVP)
### Complete ✅
- [x] Turborepo monorepo setup
- [x] Database schema (25+ models with RLS)
- [x] tRPC API (15 routers, 43 endpoints)
- [x] Supabase Auth (email, magic link, PIN, password reset)
- [x] Real-time updates (orders, tables via Supabase Realtime)
- [x] Email notifications (Resend - receipts, stock alerts)
- [x] Offline mode (PWA, IndexedDB, background sync)
- [x] Testing (324 unit tests + 5 E2E suites)
- [x] Monitoring (Sentry error tracking)
- [x] i18n (English + Arabic with RTL)
- [x] POS Terminal with cart/checkout/split payments
- [x] Kitchen Display System (KDS)
- [x] Table management with floor plan editor
- [x] Employee management with shifts
- [x] Inventory with stock alerts
- [x] Loyalty program with tiers
- [x] Bar tabs, recipes, reports
- [x] Platform admin panel
- [x] Printer integration (USB, Bluetooth, browser)

### Not Built ❌
- [ ] Multi-location UI (schema only)
- [ ] Mobile app (Capacitor)
- [ ] Online ordering portal

## TODO: Come Back To
### AI Ingredient Suggestions (partially built)
- pgvector enabled, `embedding` column on recipes, HNSW index, `match_recipes()` function
- Gemini embeddings (free) for recipe vectors, DeepSeek LLM as fallback
- Global cross-org recipe learning (all stores contribute, all stores benefit)
- Auto-embed on recipe creation (fire & forget from Add Product modal)
- Expiry-based "Use Before It Expires" widget on dashboard
- **Still needs**: Seed initial recipe embeddings, test full flow end-to-end, add AI suggestions to more screens (POS specials, inventory alerts), batch embed endpoint for backfill
- **Files**: `lib/embeddings.ts`, `api/ai/suggest-ingredients/route.ts`, `api/ai/embed-recipe/route.ts`, `components/dashboard/expiry-suggestions.tsx`

## Screens Status
### Connected & Working ✅
- Login, PIN (auth)
- POS Terminal (real products, cart, hold/recall, checkout)
- KDS Kitchen Display (real orders, start/bump, polling)
- Dashboard (metrics, recent orders, top products, expiry widget)
- Orders, Products (with Add + ingredients), Employees
- Inventory, Tables, Loyalty, Coupons, Recipes, Ingredients, Suppliers, Bar Tabs

### Polished UI Shells (backend router needed) ⏳
- Customers (feature preview), Settings (settings cards UI)

### Connected via platformAdmin router ✅
- Admin: Organizations, Users, System, Signup Requests, Partners, Audit Logs

## User Roles & Permissions
1. **Owner** - Full access including billing, multi-location management
2. **Admin** - All operations except billing management
3. **Manager** - Staff management, reports, voids, inventory
4. **Cashier** - POS access, orders, basic customer info
5. **Waiter** - Table orders, order status updates
6. **Kitchen** - KDS only, order preparation and bumping

## Demo Users (PIN Login)
- Owner: 1234
- Admin: 2345
- Manager: 3456
- Cashier: 4567
- Waiter: 5678
- Kitchen: 6789

## State Management (22 Zustand Stores)
- `auth-store.ts` - User session, org, location, role
- `cart-store.ts` - POS cart, items, modifiers, split payments
- `order-store.ts` - Orders, KDS, station routing, rush, recall
- `table-store.ts` - Tables, floor plan, merge/split, waitlist
- `product-store.ts` - Products, categories, allergens
- `customer-store.ts` - Customer data, birthdays, segments
- `employee-store.ts` - Employees, shifts, commissions, cash drawers
- `inventory-store.ts` - Stock levels, adjustments, expiry
- `loyalty-store.ts` - Points, tiers, rewards, store credit
- `held-orders-store.ts` - Hold/park orders
- `coupon-store.ts` - Coupons, promo codes
- `discount-store.ts` - Discount tracking
- `payment-store.ts` - Payment methods
- `receipt-store.ts` - Receipt generation, print/email
- `tab-store.ts` - Bar tabs, transfers
- `recipe-store.ts` - Recipes, ingredients, costs
- `supplier-store.ts` - Suppliers, purchase orders
- `modifier-store.ts` - Product modifiers
- `sync-store.ts` - Offline sync queue
- `order-context-store.ts` - Order metadata
- `printer-store.ts` - Printer settings, connection, kitchen stations

## Database
- Using Supabase for managed PostgreSQL
- Row-Level Security (RLS) for multi-tenancy
- All monetary values stored in cents
- 25+ models with relationships

## Commands
- `pnpm dev` - Start development server (port 3001)
- `pnpm build` - Build for production
- `cd apps/web && pnpm test` - Run unit tests (324 tests)
- `cd apps/web && pnpm test:watch` - Run tests in watch mode
- `cd apps/web && pnpm test:e2e` - Run Playwright E2E tests
- `pnpm db:push` - Push schema to database
- `pnpm db:studio` - Open Prisma Studio

## Code Metrics
| Metric | Count |
|--------|-------|
| TypeScript files | 164 |
| Zustand stores | 22 |
| tRPC routers | 15 |
| API endpoints | 43 |
| Pages | 33 |
| Unit tests | 324 |
| E2E test suites | 5 |

## Important Files

### tRPC API (15 Routers)
- `/apps/web/src/server/trpc.ts` - tRPC init, context, procedures
- `/apps/web/src/server/db.ts` - Supabase server client
- `/apps/web/src/server/routers/_app.ts` - Root router
- `/apps/web/src/server/routers/auth.ts` - Authentication (7 endpoints)
- `/apps/web/src/server/routers/products.ts` - Products (5 endpoints)
- `/apps/web/src/server/routers/categories.ts` - Categories (4 endpoints)
- `/apps/web/src/server/routers/customers.ts` - Customers (4 endpoints)
- `/apps/web/src/server/routers/orders.ts` - Orders, KDS (13 endpoints)
- `/apps/web/src/server/routers/employees.ts` - Employees (6 endpoints)
- `/apps/web/src/server/routers/inventory.ts` - Stock (4 endpoints)
- `/apps/web/src/server/routers/tables.ts` - Tables (5 endpoints)
- `/apps/web/src/server/routers/organization.ts` - Org settings (3 endpoints)
- `/apps/web/src/server/routers/locations.ts` - Locations (3 endpoints)
- `/apps/web/src/server/routers/notifications.ts` - Email notifications (5 endpoints)
- `/apps/web/src/server/routers/users.ts` - User management (4 endpoints)
- `/apps/web/src/server/routers/cash-drawer.ts` - Cash & EOD (3 endpoints)
- `/apps/web/src/server/routers/platform-admin.ts` - Admin (4 endpoints)

### Frontend Pages (33 Total)
- `/apps/web/src/app/pos/page.tsx` - POS Terminal
- `/apps/web/src/app/kitchen/page.tsx` - Kitchen Display
- `/apps/web/src/app/dashboard/` - 13 dashboard pages
- `/apps/web/src/app/admin/` - 4 platform admin pages
- `/apps/web/src/app/(auth)/` - Login & PIN pages

### Real-time Hooks
- `/apps/web/src/hooks/use-realtime-subscription.ts` - Supabase Realtime
- `/apps/web/src/hooks/use-orders-realtime.ts` - Orders live sync
- `/apps/web/src/hooks/use-tables-realtime.ts` - Tables live sync

### Offline & PWA
- `/apps/web/src/lib/indexed-db.ts` - IndexedDB utilities
- `/apps/web/src/lib/offline-sync.ts` - Sync queue processing
- `/apps/web/src/providers/offline-sync-provider.tsx` - Sync context

### Email
- `/apps/web/src/lib/email/index.ts` - Resend email service
- `/apps/web/src/lib/email/templates/` - HTML email templates

### Config & Utils
- `/apps/web/src/lib/permissions.ts` - Role permissions (65+ granular)
- `/apps/web/src/lib/utils.ts` - Shared utilities
- `/apps/web/src/i18n/messages/` - Translations (en.json, ar.json)
- `/packages/db/prisma/schema.prisma` - Database schema
- `/packages/db/src/database.types.ts` - Supabase generated types
- `/BANGER-POS-PLAN.md` - Full feature roadmap

## Theme
- Supports light and dark mode
- System preference detection
- Toggle in sidebar footer
- Green primary color (#16a34a light / #22c55e dark)
