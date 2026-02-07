"use client";

import { useMemo } from "react";
import { useTranslations } from "next-intl";
import { DashboardLayout, PageHeader } from "@/components/layout";
import { MetricCard } from "@/components/dashboard/metric-card";
import { TopProducts } from "@/components/dashboard/top-products";
import { RecentOrders } from "@/components/dashboard/recent-orders";
import { ExpirySuggestions } from "@/components/dashboard/expiry-suggestions";
import { useAuthStore } from "@/store/auth-store";
import { trpc } from "@/lib/trpc";
import { formatCurrency } from "@/lib/utils";

export default function DashboardPage() {
  const user = useAuthStore((s) => s.user);
  const t = useTranslations("dashboard");
  const tc = useTranslations("common");

  // Today's summary
  const { data: todaySummary, isLoading: summaryLoading } =
    trpc.orders.getTodaySummary.useQuery({});

  // Recent orders (last 8)
  const { data: recentData, isLoading: ordersLoading } =
    trpc.orders.list.useQuery({ limit: 8 });

  // Products for top products section
  const { data: productsData } = trpc.products.list.useQuery({
    isActive: true,
    limit: 100,
  });

  // Build metrics from real data
  const metrics = useMemo(() => {
    if (!todaySummary) return null;
    const avgTicket =
      todaySummary.completedOrders > 0
        ? todaySummary.revenue / todaySummary.completedOrders
        : 0;
    return [
      {
        label: t("todayRevenue"),
        value: formatCurrency(todaySummary.revenue),
        changeType: "neutral" as const,
      },
      {
        label: t("totalOrders"),
        value: String(todaySummary.totalOrders),
        changeType: "neutral" as const,
      },
      {
        label: t("avgTicket"),
        value: formatCurrency(avgTicket),
        changeType: "neutral" as const,
      },
      {
        label: t("openOrders"),
        value: String(todaySummary.openOrders),
        changeType: "neutral" as const,
      },
    ];
  }, [todaySummary]);

  // Map recent orders to display format
  const recentOrders = useMemo(() => {
    if (!recentData?.orders) return [];
    return recentData.orders.map(
      (o: {
        id: string;
        order_number: number | null;
        created_at: string;
        total: number | null;
        status: string | null;
        items: Array<{ name: string; quantity: number }>;
      }) => {
        const time = new Date(o.created_at).toLocaleTimeString("en-US", {
          hour: "numeric",
          minute: "2-digit",
          hour12: true,
        });
        const itemsStr =
          o.items
            ?.slice(0, 3)
            .map((i) => `${i.name} x${i.quantity}`)
            .join(", ") || "—";

        // Map DB status to display status
        let status: "Ready" | "Preparing" | "Completed" = "Completed";
        if (o.status === "OPEN") status = "Preparing";
        else if (o.status === "IN_PROGRESS") status = "Preparing";
        else if (o.status === "READY") status = "Ready";

        return {
          id: String(o.order_number ?? o.id.slice(0, 6)),
          time,
          items: itemsStr,
          total: formatCurrency(o.total ?? 0),
          status,
        };
      }
    );
  }, [recentData]);

  // Build top products from order items
  const topProducts = useMemo(() => {
    if (!recentData?.orders) return [];
    const productMap = new Map<string, { name: string; revenue: number }>();
    for (const order of recentData.orders as Array<{
      items: Array<{ name: string; quantity: number; total_price: number }>;
    }>) {
      for (const item of order.items ?? []) {
        const existing = productMap.get(item.name) ?? {
          name: item.name,
          revenue: 0,
        };
        existing.revenue += item.total_price ?? 0;
        productMap.set(item.name, existing);
      }
    }
    return [...productMap.values()]
      .sort((a, b) => b.revenue - a.revenue)
      .slice(0, 5)
      .map((p, i) => ({
        rank: i + 1,
        name: p.name.trim(),
        revenue: formatCurrency(p.revenue),
      }));
  }, [recentData]);

  const isLoading = summaryLoading || ordersLoading;
  const userName = user?.name?.split(" ")[0] ?? t("welcomeBack");

  return (
    <DashboardLayout>
      <div className="flex flex-col gap-6">
        {/* Page Header */}
        <PageHeader
          title={t("title")}
          description={`${t("welcomeBack")}, ${userName}`}
          actions={
            <span className="rounded-[var(--radius-pill)] border border-[var(--border)] bg-[var(--card)] px-4 py-2 font-body text-sm text-[var(--muted-foreground)]">
              {tc("today")}
            </span>
          }
        />

        {/* Metrics Row */}
        {isLoading ? (
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {[1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="flex h-[96px] animate-pulse rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]"
              />
            ))}
          </div>
        ) : metrics ? (
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {metrics.map((metric) => (
              <MetricCard key={metric.label} {...metric} />
            ))}
          </div>
        ) : null}

        {/* Charts Row */}
        <div className="flex gap-4">
          {/* Sales Overview */}
          <div className="flex flex-1 flex-col rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]">
            <div className="flex items-center justify-between border-b border-[var(--border)] px-6 py-4">
              <span className="font-brand text-base font-semibold text-[var(--foreground)]">
                {t("salesOverview")}
              </span>
            </div>
            <div className="flex h-[180px] items-center justify-center p-6">
              <span className="font-body text-sm text-[var(--muted-foreground)]">
                {t("chartComingSoon")}
              </span>
            </div>
          </div>

          {/* Top Products */}
          {topProducts.length > 0 ? (
            <TopProducts products={topProducts} />
          ) : (
            <div className="flex w-[340px] flex-col rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]">
              <div className="border-b border-[var(--border)] px-6 py-4">
                <span className="font-brand text-base font-semibold text-[var(--foreground)]">
                  {t("topProducts")}
                </span>
              </div>
              <div className="flex flex-1 items-center justify-center p-6">
                <span className="font-body text-sm text-[var(--muted-foreground)]">
                  {t("noSalesData")}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Expiry-based Recipe Suggestions */}
        <ExpirySuggestions />

        {/* Recent Orders */}
        {recentOrders.length > 0 ? (
          <RecentOrders orders={recentOrders} />
        ) : (
          <div className="flex flex-col gap-4">
            <span className="font-brand text-base font-semibold text-[var(--foreground)]">
              {t("recentOrders")}
            </span>
            <div className="flex h-32 items-center justify-center rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]">
              <span className="font-body text-sm text-[var(--muted-foreground)]">
                {t("noOrdersPrompt")}
              </span>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
