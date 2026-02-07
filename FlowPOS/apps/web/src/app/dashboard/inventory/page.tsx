"use client";

import { useState, useMemo } from "react";
import { useTranslations } from "next-intl";
import { DashboardLayout, PageHeader } from "@/components/layout";
import { Icon } from "@/components/ui";
import { cn, formatCurrency } from "@/lib/utils";
import { trpc } from "@/lib/trpc";

type MappedItem = {
  id: string;
  productId: string;
  locationId: string;
  productName: string;
  sku: string | null;
  price: number;
  location: string;
  quantity: number;
  lowStock: number;
  isLow: boolean;
  isOutOfStock: boolean;
  isActive: boolean;
};

export default function InventoryPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [lowStockOnly, setLowStockOnly] = useState(false);
  const [showAdjustModal, setShowAdjustModal] = useState(false);
  const [adjustingItem, setAdjustingItem] = useState<MappedItem | null>(null);
  const t = useTranslations("inventory");
  const tc = useTranslations("common");

  const utils = trpc.useUtils();

  const { data, isLoading } = trpc.inventory.list.useQuery({
    lowStockOnly,
    limit: 50,
  });

  const items = useMemo(() => {
    if (!data?.items) return [];
    const mapped = data.items.map((item: {
      id: string;
      product_id: string;
      location_id: string;
      quantity: number;
      low_stock: number;
      updated_at: string;
      product: {
        id: string;
        name: string;
        sku: string | null;
        barcode: string | null;
        price: number;
        image: string | null;
        is_active: boolean;
      };
      location: {
        id: string;
        name: string;
      };
    }) => ({
      id: item.id,
      productId: item.product_id,
      locationId: item.location_id,
      productName: item.product.name,
      sku: item.product.sku,
      price: item.product.price,
      location: item.location.name,
      quantity: item.quantity,
      lowStock: item.low_stock,
      isLow: item.quantity <= item.low_stock,
      isOutOfStock: item.quantity === 0,
      isActive: item.product.is_active,
      updatedAt: item.updated_at,
    }));

    if (!searchQuery) return mapped;
    const q = searchQuery.toLowerCase();
    return mapped.filter(
      (i) =>
        i.productName.toLowerCase().includes(q) ||
        (i.sku?.toLowerCase().includes(q) ?? false) ||
        i.location.toLowerCase().includes(q)
    );
  }, [data, searchQuery]);

  return (
    <DashboardLayout>
      <div className="flex flex-col gap-6">
        <PageHeader
          title={t("title")}
          description={`${data?.total ?? 0} ${t("trackedItems")}`}
          actions={
            <button
              onClick={() => setShowAdjustModal(true)}
              className="flex items-center gap-2 rounded-[var(--radius-pill)] bg-[var(--primary)] px-4 py-2 font-brand text-sm font-medium text-white transition-colors hover:bg-[var(--primary)]/90"
            >
              <Icon name="tune" size={18} />
              {t("adjustStock")}
            </button>
          }
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
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("sku")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("location")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("price")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("quantity")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("lowStock")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("status")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("actions")}</th>
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
                      {item.productName}
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {item.sku ?? "\u2014"}
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {item.location}
                    </td>
                    <td className="px-4 py-3 font-brand text-sm font-medium text-[var(--foreground)]">
                      {formatCurrency(item.price)}
                    </td>
                    <td className="px-4 py-3 font-brand text-sm font-medium text-[var(--foreground)]">
                      {item.quantity}
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {item.lowStock}
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
                    <td className="px-4 py-3">
                      <button
                        onClick={() => setAdjustingItem(item)}
                        className="rounded-full p-1.5 text-[var(--muted-foreground)] hover:bg-[var(--accent)] hover:text-[var(--foreground)] transition-colors"
                        title={t("adjustStock")}
                      >
                        <Icon name="tune" size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {(showAdjustModal || adjustingItem) && (
        <AdjustStockModal
          item={adjustingItem}
          onClose={() => { setShowAdjustModal(false); setAdjustingItem(null); }}
          onSuccess={() => {
            setShowAdjustModal(false);
            setAdjustingItem(null);
            utils.inventory.list.invalidate();
          }}
        />
      )}
    </DashboardLayout>
  );
}

/* ─── Adjust Stock Modal ────────────────────────────── */

function AdjustStockModal({
  item,
  onClose,
  onSuccess,
}: {
  item: MappedItem | null;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [adjustment, setAdjustment] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const t = useTranslations("inventory");
  const tc = useTranslations("common");

  const adjustMutation = trpc.inventory.adjust.useMutation({
    onError: (err) => setError(err.message),
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!item) { setError("Please select an item from the table"); return; }
    const adj = Number(adjustment);
    if (!adjustment || adj === 0) { setError("Enter a non-zero adjustment amount"); return; }

    await adjustMutation.mutateAsync({
      productId: item.productId,
      locationId: item.locationId,
      adjustment: adj,
      reason: reason.trim() || undefined,
    });
    onSuccess();
  };

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/40" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="w-full max-w-sm rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] shadow-xl" onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center justify-between border-b border-[var(--border)] px-6 py-4">
            <h2 className="font-brand text-lg font-semibold text-[var(--foreground)]">{t("adjustStock")}</h2>
            <button onClick={onClose} className="rounded-full p-1 text-[var(--muted-foreground)] hover:bg-[var(--accent)]">
              <Icon name="close" size={20} />
            </button>
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4 px-6 py-5">
            {error && (
              <div className="rounded-[var(--radius-m)] bg-red-50 px-3 py-2 font-body text-xs text-red-600 dark:bg-red-900/20 dark:text-red-400">
                {error}
              </div>
            )}

            {item && (
              <div className="rounded-[var(--radius-m)] bg-[var(--accent)] px-3 py-2">
                <span className="font-brand text-sm font-medium text-[var(--foreground)]">{item.productName}</span>
                <span className="font-body text-sm text-[var(--muted-foreground)]"> at {item.location}</span>
                <div className="font-body text-xs text-[var(--muted-foreground)]">{t("currentStock")} {item.quantity}</div>
              </div>
            )}

            {!item && (
              <p className="font-body text-sm text-[var(--muted-foreground)]">
                Close this dialog and click the adjust button on a specific item row.
              </p>
            )}

            <div className="flex flex-col gap-1.5">
              <label className="font-body text-sm font-medium text-[var(--foreground)]">
                {t("adjustment")} <span className="text-[var(--destructive)]">*</span>
              </label>
              <input type="number" step="1" value={adjustment} onChange={(e) => setAdjustment(e.target.value)} placeholder="+10 or -5"
                className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]" />
              <span className="font-body text-xs text-[var(--muted-foreground)]">{t("adjustmentHint")}</span>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="font-body text-sm font-medium text-[var(--foreground)]">{t("reason")}</label>
              <input type="text" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Restock, waste, count correction..."
                className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]" />
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button type="button" onClick={onClose}
                className="rounded-[var(--radius-pill)] px-4 py-2 font-brand text-sm text-[var(--foreground)] hover:bg-[var(--accent)] transition-colors">
                {tc("cancel")}
              </button>
              <button type="submit" disabled={adjustMutation.isPending || !item || !adjustment}
                className="flex items-center gap-2 rounded-[var(--radius-pill)] bg-[var(--primary)] px-5 py-2 font-brand text-sm font-medium text-white transition-colors hover:bg-[var(--primary)]/90 disabled:opacity-50">
                {adjustMutation.isPending ? t("adjusting") : t("applyAdjustment")}
              </button>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}
