"use client";

import { useState, useEffect, useMemo, useCallback } from "react";
import { useTranslations } from "next-intl";
import { DashboardLayout, PageHeader } from "@/components/layout";
import { Icon } from "@/components/ui";
import { cn, formatCurrency } from "@/lib/utils";
import { getPlaces, getDataOrders, type DataOrder } from "@/lib/forecasting-api";
import { usePOSOrdersStore } from "@/store/pos-orders-store";

const STATUS_FILTERS = ["All", "Closed", "Pending", "Cancelled"];

const STATUS_COLORS: Record<string, string> = {
  Closed: "bg-[var(--secondary)] text-[var(--muted-foreground)]",
  Pending: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  Cancelled: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  Unknown: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
};

export default function OrdersPage() {
  const [statusFilter, setStatusFilter] = useState("All");
  const [searchQuery, setSearchQuery] = useState("");
  const t = useTranslations("orders");
  const tc = useTranslations("common");

  // Places state
  const [places, setPlaces] = useState<{ id: number; title: string; order_count: number }[]>([]);
  const [placesLoading, setPlacesLoading] = useState(true);
  const [placeId, setPlaceId] = useState<number | null>(null);

  // Orders state
  const [orders, setOrders] = useState<DataOrder[]>([]);
  const [totalOrders, setTotalOrders] = useState(0);
  const [ordersLoading, setOrdersLoading] = useState(false);
  const [page, setPage] = useState(0);
  const pageSize = 50;

  // Fetch places on mount
  useEffect(() => {
    let cancelled = false;
    setPlacesLoading(true);
    getPlaces()
      .then((res) => {
        if (cancelled) return;
        setPlaces(res.places);
        if (res.places.length > 0) {
          setPlaceId(res.places[0].id);
        }
      })
      .catch((err) => {
        if (!cancelled) console.error("Failed to load places:", err);
      })
      .finally(() => {
        if (!cancelled) setPlacesLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  // Fetch orders when placeId, statusFilter, or page changes
  const fetchOrders = useCallback(() => {
    if (placeId == null) return;
    let cancelled = false;
    setOrdersLoading(true);
    getDataOrders({
      placeId,
      status: statusFilter !== "All" ? statusFilter : undefined,
      limit: pageSize,
      offset: page * pageSize,
    })
      .then((res) => {
        if (cancelled) return;
        setOrders(res.orders);
        setTotalOrders(res.total);
      })
      .catch((err) => {
        if (!cancelled) console.error("Failed to load orders:", err);
      })
      .finally(() => {
        if (!cancelled) setOrdersLoading(false);
      });
    return () => { cancelled = true; };
  }, [placeId, statusFilter, page]);

  useEffect(() => {
    return fetchOrders();
  }, [fetchOrders]);

  // Reset page when filters change
  useEffect(() => {
    setPage(0);
  }, [placeId, statusFilter]);

  // Merge POS orders (from local store) with dataset orders
  const posOrders = usePOSOrdersStore((s) => s.orders);

  const allOrders = useMemo(() => {
    // Convert POS orders to DataOrder shape and prepend them
    const mapped: DataOrder[] = posOrders.map((po) => ({
      id: 0,
      code: po.code,
      status: po.status,
      type: po.type,
      total_amount: po.total_amount,
      items_amount: po.items_amount,
      discount_amount: po.discount_amount,
      payment_method: po.payment_method,
      customer_name: po.customer_name,
      channel: po.channel,
      place_name: po.place_name,
      created: po.created,
      items: po.items,
    }));
    return [...mapped, ...orders];
  }, [posOrders, orders]);

  // Client-side search on loaded orders
  const filteredOrders = useMemo(() => {
    // Apply status filter to POS orders too
    let filtered = allOrders;
    if (statusFilter !== "All") {
      filtered = filtered.filter((o) => o.status === statusFilter);
    } else {
      filtered = allOrders;
    }
    if (!searchQuery) return filtered;
    const q = searchQuery.toLowerCase();
    return filtered.filter(
      (o) =>
        String(o.id).includes(q) ||
        (o.code?.toLowerCase().includes(q) ?? false) ||
        (o.customer_name?.toLowerCase().includes(q) ?? false) ||
        o.items.some((i) => i.title.toLowerCase().includes(q))
    );
  }, [allOrders, statusFilter, searchQuery]);

  const isLoading = placesLoading || ordersLoading;
  const totalPages = Math.ceil(totalOrders / pageSize);

  return (
    <DashboardLayout>
      <div className="flex flex-col gap-6">
        <PageHeader
          title={t("title")}
          description={`${totalOrders.toLocaleString()} ${t("totalCount")}`}
        />

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-4">
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
          <select
            value={placeId ?? ""}
            onChange={(e) => setPlaceId(Number(e.target.value))}
            disabled={placesLoading}
            className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--ring)] disabled:opacity-50"
          >
            {placesLoading ? (
              <option>Loading...</option>
            ) : (
              places.map((place) => (
                <option key={place.id} value={place.id}>
                  {place.title}
                </option>
              ))
            )}
          </select>
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
                {status === "All" ? tc("all") : status}
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
        ) : filteredOrders.length === 0 ? (
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
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">Customer</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("total")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("status")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("time")}</th>
                </tr>
              </thead>
              <tbody>
                {filteredOrders.map((order, idx) => {
                  const itemsSummary = order.items
                    .slice(0, 2)
                    .map((i) => `${i.quantity}x ${i.title}`)
                    .join(", ");
                  const moreCount = order.items.length - 2;
                  return (
                    <tr
                      key={order.id}
                      className={cn(
                        "bg-[var(--card)] hover:bg-[var(--accent)] transition-colors",
                        idx < filteredOrders.length - 1 && "border-b border-[var(--border)]"
                      )}
                    >
                      <td className="px-4 py-3 font-brand text-sm font-medium text-[var(--foreground)]">
                        #{order.code ?? order.id}
                      </td>
                      <td className="px-4 py-3 font-body text-sm text-[var(--foreground)] max-w-[280px]">
                        <span className="truncate block">
                          {itemsSummary || "\u2014"}
                          {moreCount > 0 && (
                            <span className="text-[var(--muted-foreground)]"> +{moreCount} more</span>
                          )}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                        {order.type ?? "\u2014"}
                      </td>
                      <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                        {order.customer_name ?? "\u2014"}
                      </td>
                      <td className="px-4 py-3 font-brand text-sm font-medium text-[var(--foreground)]">
                        {formatCurrency(Math.round(order.total_amount * 100))}
                      </td>
                      <td className="px-4 py-3">
                        <span className={cn(
                          "inline-flex rounded-[var(--radius-pill)] px-2.5 py-0.5 font-body text-xs font-medium",
                          STATUS_COLORS[order.status] ?? STATUS_COLORS.Unknown
                        )}>
                          {order.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                        {order.created
                          ? new Date(order.created * 1000).toLocaleString("en-US", {
                              month: "short",
                              day: "numeric",
                              year: "numeric",
                              hour: "numeric",
                              minute: "2-digit",
                              hour12: true,
                            })
                          : "\u2014"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between">
            <span className="font-body text-sm text-[var(--muted-foreground)]">
              Page {page + 1} of {totalPages}
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="flex items-center gap-1 rounded-[var(--radius-pill)] px-3 py-1.5 font-body text-xs text-[var(--foreground)] transition-colors hover:bg-[var(--accent)] disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Icon name="chevron_left" size={16} />
                Previous
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="flex items-center gap-1 rounded-[var(--radius-pill)] px-3 py-1.5 font-body text-xs text-[var(--foreground)] transition-colors hover:bg-[var(--accent)] disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Next
                <Icon name="chevron_right" size={16} />
              </button>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
