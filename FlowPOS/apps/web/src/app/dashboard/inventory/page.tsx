"use client";

import { useState, useEffect, useMemo } from "react";
import { useTranslations } from "next-intl";
import { DashboardLayout, PageHeader } from "@/components/layout";
import { Icon } from "@/components/ui";
import { cn, formatCurrency } from "@/lib/utils";
import { getInventory } from "@/lib/forecasting-api";

type InventoryItem = {
  id: number;
  title: string;
  price: number | null;
  status: string | null;
  quantity: number | null;
  threshold: number | null;
  unit: string | null;
  category_name: string | null;
};

export default function InventoryPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [lowStockOnly, setLowStockOnly] = useState(false);
  const t = useTranslations("inventory");
  const tc = useTranslations("common");

  const [rawItems, setRawItems] = useState<InventoryItem[]>([]);
  const [totalItems, setTotalItems] = useState(0);
  const [lowStockCount, setLowStockCount] = useState(0);
  const [isLoading, setIsLoading] = useState(true);

  // Fetch inventory on mount
  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    getInventory(500)
      .then((res) => {
        if (cancelled) return;
        setRawItems(res.items as InventoryItem[]);
        setTotalItems(res.total_items);
        setLowStockCount(res.low_stock_count);
      })
      .catch((err) => {
        if (!cancelled) console.error("Failed to load inventory:", err);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const items = useMemo(() => {
    let filtered = rawItems.map((item) => {
      const qty = item.quantity ?? 0;
      const thresh = item.threshold ?? 0;
      return {
        ...item,
        qty,
        thresh,
        isLow: thresh > 0 && qty <= thresh,
        isOutOfStock: qty === 0,
      };
    });

    if (lowStockOnly) {
      filtered = filtered.filter((i) => i.isLow || i.isOutOfStock);
    }

    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (i) =>
          i.title?.toLowerCase().includes(q) ||
          (i.category_name?.toLowerCase().includes(q) ?? false)
      );
    }

    return filtered;
  }, [rawItems, searchQuery, lowStockOnly]);

  return (
    <DashboardLayout>
      <div className="flex flex-col gap-6">
        <PageHeader
          title={t("title")}
          description={`${totalItems} ${t("trackedItems")}${lowStockCount > 0 ? ` \u2022 ${lowStockCount} low stock` : ""}`}
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
            {([
              { key: false, label: tc("all") },
              { key: true, label: t("lowStock") },
            ] as const).map((filter) => (
              <button
                key={String(filter.key)}
                onClick={() => setLowStockOnly(filter.key)}
                className={cn(
                  "rounded-[var(--radius-pill)] px-3 py-1.5 font-body text-xs transition-colors",
                  lowStockOnly === filter.key
                    ? "bg-[var(--primary)] font-medium text-white"
                    : "bg-[var(--secondary)] text-[var(--muted-foreground)] hover:bg-[var(--accent)]"
                )}
              >
                {filter.label}
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
        ) : items.length === 0 ? (
          <div className="flex h-64 items-center justify-center rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]">
            <div className="flex flex-col items-center gap-2 text-[var(--muted-foreground)]">
              <Icon name="inventory_2" size={40} />
              <span className="font-body text-sm">{t("noItems")}</span>
            </div>
          </div>
        ) : (
          <div className="overflow-hidden rounded-[var(--radius-m)] border border-[var(--border)]">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--card)]">
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("product")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">Category</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("price")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("quantity")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">Threshold</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("status")}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item, idx) => (
                  <tr
                    key={item.id}
                    className={cn(
                      "bg-[var(--card)] hover:bg-[var(--accent)] transition-colors",
                      idx < items.length - 1 && "border-b border-[var(--border)]"
                    )}
                  >
                    <td className="px-4 py-3 font-brand text-sm font-medium text-[var(--foreground)]">
                      {item.title}
                    </td>
                    <td className="px-4 py-3">
                      {item.category_name ? (
                        <span className="rounded-[var(--radius-pill)] bg-[var(--secondary)] px-2.5 py-0.5 font-body text-xs text-[var(--muted-foreground)]">
                          {item.category_name}
                        </span>
                      ) : (
                        <span className="font-body text-sm text-[var(--muted-foreground)]">{"\u2014"}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 font-brand text-sm font-medium text-[var(--foreground)]">
                      {item.price != null ? formatCurrency(Math.round(item.price * 100)) : "\u2014"}
                    </td>
                    <td className="px-4 py-3 font-brand text-sm font-medium text-[var(--foreground)]">
                      {item.qty}{item.unit ? ` ${item.unit}` : ""}
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {item.thresh > 0 ? item.thresh : "\u2014"}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={cn(
                          "inline-flex rounded-[var(--radius-pill)] px-2.5 py-0.5 font-body text-xs font-medium",
                          item.isOutOfStock
                            ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                            : item.isLow
                              ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
                              : "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                        )}
                      >
                        {item.isOutOfStock ? t("outOfStock") : item.isLow ? t("lowStock") : t("inStock")}
                      </span>
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
