"use client";

import { useState, useMemo } from "react";
import { useTranslations } from "next-intl";
import { DashboardLayout, PageHeader } from "@/components/layout";
import { Icon } from "@/components/ui";
import { cn, formatCurrency } from "@/lib/utils";
import { trpc } from "@/lib/trpc";

const STATUS_FILTERS = ["All", "OPEN", "IN_PROGRESS", "READY", "COMPLETED", "CANCELLED"];

const useStatusLabels = () => {
  const t = useTranslations("orders");
  return {
    OPEN: t("open"),
    IN_PROGRESS: t("inProgress"),
    READY: t("ready"),
    COMPLETED: t("completed"),
    CANCELLED: t("cancelled"),
    REFUNDED: t("refunded"),
  };
};

const STATUS_COLORS: Record<string, string> = {
  OPEN: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  IN_PROGRESS: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  READY: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  COMPLETED: "bg-[var(--secondary)] text-[var(--muted-foreground)]",
  CANCELLED: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  REFUNDED: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
};

export default function OrdersPage() {
  const [statusFilter, setStatusFilter] = useState("All");
  const [searchQuery, setSearchQuery] = useState("");
  const t = useTranslations("orders");
  const tc = useTranslations("common");
  const STATUS_LABELS = useStatusLabels();

  const queryInput = useMemo(() => {
    const input: { status?: "OPEN" | "IN_PROGRESS" | "READY" | "COMPLETED" | "CANCELLED"; limit: number } = { limit: 50 };
    if (statusFilter !== "All") {
      input.status = statusFilter as "OPEN" | "IN_PROGRESS" | "READY" | "COMPLETED" | "CANCELLED";
    }
    return input;
  }, [statusFilter]);

  const { data, isLoading } = trpc.orders.list.useQuery(queryInput);

  const orders = useMemo(() => {
    if (!data?.orders) return [];
    const mapped = data.orders.map((o: {
      id: string;
      order_number: number | null;
      status: string | null;
      type: string | null;
      total: number | null;
      created_at: string;
      table: { name: string } | null;
      customer: { name: string } | null;
      employee: { user: { email: string } | null } | null;
      items: Array<{ name: string; quantity: number }>;
    }) => ({
      id: o.id,
      orderNumber: o.order_number ?? 0,
      status: o.status ?? "OPEN",
      type: o.type ?? "DINE_IN",
      total: o.total ?? 0,
      createdAt: o.created_at,
      table: o.table?.name ?? null,
      customer: o.customer?.name ?? null,
      employee: o.employee?.user?.email ?? null,
      itemCount: o.items?.length ?? 0,
      itemsSummary: o.items?.slice(0, 2).map((i) => `${i.quantity}x ${i.name}`).join(", ") ?? "",
    }));

    if (!searchQuery) return mapped;
    const q = searchQuery.toLowerCase();
    return mapped.filter(
      (o) =>
        String(o.orderNumber).includes(q) ||
        o.itemsSummary.toLowerCase().includes(q) ||
        (o.customer?.toLowerCase().includes(q) ?? false)
    );
  }, [data, searchQuery]);

  return (
    <DashboardLayout>
      <div className="flex flex-col gap-6">
        <PageHeader
          title={t("title")}
          description={`${data?.total ?? 0} ${t("totalCount")}`}
        />

        {/* Filters */}
        <div className="flex items-center gap-4">
          <div className="relative flex-1 max-w-sm">
            <Icon
              name="search"
              size={18}
              className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]"
            />
            <input
              type="text"
              placeholder={t("searchPlaceholder")}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-10 w-full rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] ps-10 pe-4 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--ring)]"
            />
          </div>
          <div className="flex items-center gap-2">
            {STATUS_FILTERS.map((status) => (
              <button
                key={status}
                onClick={() => setStatusFilter(status)}
                className={cn(
                  "rounded-[var(--radius-pill)] px-3 py-1.5 font-body text-xs transition-colors",
                  statusFilter === status
                    ? "bg-[var(--primary)] font-medium text-white"
                    : "bg-[var(--secondary)] text-[var(--muted-foreground)] hover:bg-[var(--accent)]"
                )}
              >
                {status === "All" ? tc("all") : STATUS_LABELS[status as keyof typeof STATUS_LABELS] ?? status}
              </button>
            ))}
          </div>
        </div>

        {/* Table */}
        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
              <span className="font-body text-sm text-[var(--muted-foreground)]">{t("loading")}</span>
            </div>
          </div>
        ) : orders.length === 0 ? (
          <div className="flex h-64 items-center justify-center rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]">
            <div className="flex flex-col items-center gap-2 text-[var(--muted-foreground)]">
              <Icon name="receipt_long" size={40} />
              <span className="font-body text-sm">{t("noOrders")}</span>
            </div>
          </div>
        ) : (
          <div className="overflow-hidden rounded-[var(--radius-m)] border border-[var(--border)]">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--card)]">
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("order")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("items")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("type")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("table")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("total")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("status")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("time")}</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((order, idx) => (
                  <tr
                    key={order.id}
                    className={cn(
                      "bg-[var(--card)] hover:bg-[var(--accent)] transition-colors",
                      idx < orders.length - 1 && "border-b border-[var(--border)]"
                    )}
                  >
                    <td className="px-4 py-3 font-brand text-sm font-medium text-[var(--foreground)]">
                      #{order.orderNumber}
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--foreground)] max-w-[250px] truncate">
                      {order.itemsSummary || "—"}
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {order.type.replace("_", " ")}
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {order.table ?? "—"}
                    </td>
                    <td className="px-4 py-3 font-brand text-sm font-medium text-[var(--foreground)]">
                      {formatCurrency(order.total)}
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn(
                        "inline-flex rounded-[var(--radius-pill)] px-2.5 py-0.5 font-body text-xs font-medium",
                        STATUS_COLORS[order.status] ?? STATUS_COLORS.OPEN
                      )}>
                        {STATUS_LABELS[order.status as keyof typeof STATUS_LABELS] ?? order.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {new Date(order.createdAt).toLocaleString("en-US", {
                        month: "short",
                        day: "numeric",
                        hour: "numeric",
                        minute: "2-digit",
                        hour12: true,
                      })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
