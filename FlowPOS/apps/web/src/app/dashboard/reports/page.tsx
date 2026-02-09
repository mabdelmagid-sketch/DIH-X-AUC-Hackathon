"use client";

import { useMemo } from "react";
import { useTranslations } from "next-intl";
import { DashboardLayout, PageHeader } from "@/components/layout";
import { Icon } from "@/components/ui";
import { cn, formatCurrency } from "@/lib/utils";
import { trpc } from "@/lib/trpc";

const STATUS_ORDER = ["OPEN", "IN_PROGRESS", "READY", "COMPLETED", "CANCELLED"] as const;

const STATUS_LABELS: Record<string, string> = {
  OPEN: "Open",
  IN_PROGRESS: "In Progress",
  READY: "Ready",
  COMPLETED: "Completed",
  CANCELLED: "Cancelled",
};

const STATUS_COLORS: Record<string, string> = {
  OPEN: "bg-sky-400",
  IN_PROGRESS: "bg-amber-400",
  READY: "bg-teal-400",
  COMPLETED: "bg-emerald-500",
  CANCELLED: "bg-rose-400",
};

const STATUS_BADGE_COLORS: Record<string, string> = {
  OPEN: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  IN_PROGRESS: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  READY: "bg-teal-100 text-teal-700 dark:bg-teal-900/40 dark:text-teal-300",
  COMPLETED: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  CANCELLED: "bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300",
};

export default function ReportsPage() {
  const t = useTranslations("reports");
  const tc = useTranslations("common");

  const { data: summary, isLoading: summaryLoading } =
    trpc.orders.getTodaySummary.useQuery({});

  const { data: ordersData, isLoading: ordersLoading } =
    trpc.orders.list.useQuery({ limit: 50 });

  const isLoading = summaryLoading || ordersLoading;

  // Derive status breakdown and extra metrics from the orders list
  const { statusBreakdown, cancelledOrders, averageOrderValue, maxCount } =
    useMemo(() => {
      const orders = ordersData?.orders ?? [];

      const breakdown: Record<string, number> = {
        OPEN: 0,
        IN_PROGRESS: 0,
        READY: 0,
        COMPLETED: 0,
        CANCELLED: 0,
      };

      let completedTotal = 0;
      let completedCount = 0;

      for (const order of orders) {
        const status = (order as { status: string | null }).status ?? "OPEN";
        if (status in breakdown) {
          breakdown[status]++;
        }
        if (status === "COMPLETED") {
          completedCount++;
          completedTotal += (order as { total: number | null }).total ?? 0;
        }
      }

      return {
        statusBreakdown: breakdown,
        cancelledOrders: breakdown.CANCELLED,
        averageOrderValue: completedCount > 0 ? completedTotal / completedCount : 0,
        maxCount: Math.max(...Object.values(breakdown), 1),
      };
    }, [ordersData]);

  // Summary metric cards configuration
  const metrics = [
    {
      label: t("revenue"),
      value: formatCurrency(summary?.revenue ?? 0),
      icon: "payments",
      color: "text-white",
      bgColor: "bg-emerald-500",
    },
    {
      label: t("totalOrders"),
      value: String(summary?.totalOrders ?? 0),
      icon: "receipt_long",
      color: "text-white",
      bgColor: "bg-sky-500",
    },
    {
      label: t("completed"),
      value: String(summary?.completedOrders ?? 0),
      icon: "check_circle",
      color: "text-white",
      bgColor: "bg-teal-500",
    },
    {
      label: t("cancelled"),
      value: String(cancelledOrders),
      icon: "cancel",
      color: "text-white",
      bgColor: "bg-rose-500",
    },
    {
      label: t("avgOrderValue"),
      value: formatCurrency(Math.round(averageOrderValue)),
      icon: "trending_up",
      color: "text-white",
      bgColor: "bg-violet-500",
    },
  ];

  return (
    <DashboardLayout>
      <div className="flex flex-col gap-6">
        <PageHeader
          title={t("title")}
          description={t("description")}
          actions={
            <span className="inline-flex items-center gap-1.5 rounded-[var(--radius-pill)] bg-[var(--secondary)] px-3 py-1.5 font-body text-xs text-[var(--muted-foreground)]">
              <Icon name="today" size={14} />
              {tc("today")}
            </span>
          }
        />

        {/* Loading state */}
        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
              <span className="font-body text-sm text-[var(--muted-foreground)]">
                {t("loading")}
              </span>
            </div>
          </div>
        ) : (
          <>
            {/* Summary metrics */}
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
              {metrics.map((metric) => (
                <div
                  key={metric.label}
                  className="flex flex-col gap-3 rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] p-4"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-body text-xs text-[var(--muted-foreground)]">
                      {metric.label}
                    </span>
                    <div
                      className={cn(
                        "flex h-8 w-8 items-center justify-center rounded-[var(--radius-m)]",
                        metric.bgColor
                      )}
                    >
                      <Icon name={metric.icon} size={16} className={metric.color} />
                    </div>
                  </div>
                  <span className="font-brand text-xl font-bold text-[var(--foreground)]">
                    {metric.value}
                  </span>
                </div>
              ))}
            </div>

            {/* Status breakdown */}
            <div className="rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] p-6">
              <div className="mb-6 flex items-center justify-between">
                <div>
                  <h2 className="font-brand text-base font-semibold text-[var(--foreground)]">
                    {t("ordersByStatus")}
                  </h2>
                  <p className="mt-0.5 font-body text-xs text-[var(--muted-foreground)]">
                    {t("statusBreakdown")}
                  </p>
                </div>
                <div className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-m)] bg-[var(--secondary)]">
                  <Icon name="bar_chart" size={18} className="text-[var(--muted-foreground)]" />
                </div>
              </div>

              {/* Bar chart */}
              <div className="flex flex-col gap-4">
                {STATUS_ORDER.map((status) => {
                  const count = statusBreakdown[status] ?? 0;
                  const percentage = maxCount > 0 ? (count / maxCount) * 100 : 0;

                  return (
                    <div key={status} className="flex items-center gap-4">
                      <div className="w-28 shrink-0">
                        <span
                          className={cn(
                            "inline-flex rounded-[var(--radius-pill)] px-2.5 py-0.5 font-body text-xs font-medium",
                            STATUS_BADGE_COLORS[status]
                          )}
                        >
                          {STATUS_LABELS[status]}
                        </span>
                      </div>
                      <div className="flex flex-1 items-center gap-3">
                        <div className="relative h-8 flex-1 overflow-hidden rounded-[var(--radius-m)] bg-[var(--secondary)]">
                          <div
                            className={cn(
                              "absolute inset-y-0 start-0 rounded-[var(--radius-m)] transition-all duration-500",
                              STATUS_COLORS[status]
                            )}
                            style={{ width: `${percentage}%`, minWidth: count > 0 ? "8px" : "0px" }}
                          />
                        </div>
                        <span className="w-8 shrink-0 text-end font-brand text-sm font-semibold text-[var(--foreground)]">
                          {count}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Quick stats row */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {/* Active orders */}
              <div className="flex items-center gap-4 rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] p-5">
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-sky-500">
                  <Icon name="pending_actions" size={24} className="text-white" />
                </div>
                <div className="flex flex-col">
                  <span className="font-body text-xs text-[var(--muted-foreground)]">
                    {t("activeOrders")}
                  </span>
                  <span className="font-brand text-2xl font-bold text-[var(--foreground)]">
                    {summary?.openOrders ?? 0}
                  </span>
                  <span className="font-body text-xs text-[var(--muted-foreground)]">
                    {t("activeDescription")}
                  </span>
                </div>
              </div>

              {/* Completion rate */}
              <div className="flex items-center gap-4 rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] p-5">
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500">
                  <Icon name="percent" size={24} className="text-white" />
                </div>
                <div className="flex flex-col">
                  <span className="font-body text-xs text-[var(--muted-foreground)]">
                    {t("completionRate")}
                  </span>
                  <span className="font-brand text-2xl font-bold text-[var(--foreground)]">
                    {(summary?.totalOrders ?? 0) > 0
                      ? Math.round(
                          ((summary?.completedOrders ?? 0) /
                            (summary?.totalOrders ?? 1)) *
                            100
                        )
                      : 0}
                    %
                  </span>
                  <span className="font-body text-xs text-[var(--muted-foreground)]">
                    {t("ofOrders", {
                      completed: summary?.completedOrders ?? 0,
                      total: summary?.totalOrders ?? 0,
                    })}
                  </span>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </DashboardLayout>
  );
}
