"use client";

import { useState, useMemo } from "react";
import { useTranslations } from "next-intl";
import { DashboardLayout, PageHeader } from "@/components/layout";
import { Icon } from "@/components/ui";
import { cn, formatCurrency } from "@/lib/utils";
import { trpc } from "@/lib/trpc";

const COUPON_TYPES = ["percentage", "fixed", "bogo", "free_item"] as const;

function getTypeLabels(t: (key: string) => string): Record<string, string> {
  return {
    percentage: t("typePercentage"),
    fixed: t("typeFixed"),
    bogo: t("typeBogo"),
    free_item: t("typeFreeItem"),
  };
}

type MappedCoupon = {
  id: string;
  code: string;
  name: string;
  type: string;
  value: number;
  minOrderAmount: number | null;
  maxUses: number | null;
  usedCount: number;
  validFrom: string;
  validUntil: string;
  isActive: boolean;
  isExpired: boolean;
};

export default function CouponsPage() {
  const t = useTranslations("coupons");
  const tc = useTranslations("common");

  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState<"all" | "active" | "inactive">("all");
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingCoupon, setEditingCoupon] = useState<MappedCoupon | null>(null);
  const [deletingCoupon, setDeletingCoupon] = useState<MappedCoupon | null>(null);

  const utils = trpc.useUtils();
  const { data, isLoading } = trpc.coupons.list.useQuery({
    ...(activeFilter === "active" ? { isActive: true } : activeFilter === "inactive" ? { isActive: false } : {}),
    limit: 50,
  });

  const coupons = useMemo(() => {
    if (!data?.coupons) return [];
    const mapped: MappedCoupon[] = (data.coupons as Array<{
      id: string;
      code: string;
      name: string;
      type: string;
      value: number;
      min_order_amount: number | null;
      max_uses: number | null;
      used_count: number;
      valid_from: string;
      valid_until: string;
      is_active: boolean;
    }>).map((c) => ({
      id: c.id,
      code: c.code,
      name: c.name,
      type: c.type,
      value: c.value,
      minOrderAmount: c.min_order_amount,
      maxUses: c.max_uses,
      usedCount: c.used_count ?? 0,
      validFrom: c.valid_from,
      validUntil: c.valid_until,
      isActive: c.is_active,
      isExpired: new Date(c.valid_until) < new Date(),
    }));

    if (!searchQuery) return mapped;
    const q = searchQuery.toLowerCase();
    return mapped.filter(
      (c) =>
        c.code.toLowerCase().includes(q) ||
        c.name.toLowerCase().includes(q)
    );
  }, [data, searchQuery]);

  return (
    <DashboardLayout>
      <div className="flex flex-col gap-6">
        <PageHeader
          title={t("title")}
          description={`${data?.total ?? 0} ${t("couponsCount")}`}
          actions={
            <button
              onClick={() => setShowAddModal(true)}
              className="flex items-center gap-2 rounded-[var(--radius-pill)] bg-[var(--primary)] px-4 py-2 font-brand text-sm font-medium text-white transition-colors hover:bg-[var(--primary)]/90"
            >
              <Icon name="add" size={18} />
              {t("createCoupon")}
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
            {(["all", "active", "inactive"] as const).map((filter) => (
              <button
                key={filter}
                onClick={() => setActiveFilter(filter)}
                className={cn(
                  "rounded-[var(--radius-pill)] px-3 py-1.5 font-body text-xs capitalize transition-colors",
                  activeFilter === filter
                    ? "bg-[var(--primary)] font-medium text-white"
                    : "bg-[var(--secondary)] text-[var(--muted-foreground)] hover:bg-[var(--accent)]"
                )}
              >
                {filter === "all" ? tc("all") : filter === "active" ? tc("active") : tc("inactive")}
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
        ) : coupons.length === 0 ? (
          <div className="flex h-64 items-center justify-center rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]">
            <div className="flex flex-col items-center gap-2 text-[var(--muted-foreground)]">
              <Icon name="confirmation_number" size={40} />
              <span className="font-body text-sm">{t("noCoupons")}</span>
            </div>
          </div>
        ) : (
          <div className="overflow-hidden rounded-[var(--radius-m)] border border-[var(--border)]">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--card)]">
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("code")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("name")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("type")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("value")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("usage")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("validUntil")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("status")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {coupons.map((coupon, idx) => (
                  <tr
                    key={coupon.id}
                    className={cn(
                      "bg-[var(--card)] hover:bg-[var(--accent)] transition-colors",
                      idx < coupons.length - 1 && "border-b border-[var(--border)]"
                    )}
                  >
                    <td className="px-4 py-3 font-brand text-sm font-medium text-[var(--foreground)]">
                      {coupon.code}
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--foreground)]">
                      {coupon.name}
                    </td>
                    <td className="px-4 py-3">
                      <span className="rounded-[var(--radius-pill)] bg-[var(--secondary)] px-2.5 py-0.5 font-body text-xs text-[var(--muted-foreground)]">
                        {getTypeLabels(t)[coupon.type] ?? coupon.type}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-brand text-sm font-medium text-[var(--foreground)]">
                      {coupon.type === "percentage"
                        ? `${coupon.value}%`
                        : coupon.type === "fixed"
                          ? formatCurrency(coupon.value)
                          : "\u2014"}
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {coupon.usedCount}{coupon.maxUses ? ` / ${coupon.maxUses}` : ""}
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {new Date(coupon.validUntil).toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                        year: "numeric",
                      })}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={cn(
                          "inline-flex rounded-[var(--radius-pill)] px-2.5 py-0.5 font-body text-xs font-medium",
                          coupon.isExpired
                            ? "bg-[var(--secondary)] text-[var(--muted-foreground)]"
                            : coupon.isActive
                              ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                              : "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                        )}
                      >
                        {coupon.isExpired ? t("expired") : coupon.isActive ? tc("active") : tc("inactive")}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => setEditingCoupon(coupon)}
                          className="rounded-full p-1.5 text-[var(--muted-foreground)] hover:bg-[var(--accent)] hover:text-[var(--foreground)] transition-colors"
                        >
                          <Icon name="edit" size={16} />
                        </button>
                        <button
                          onClick={() => setDeletingCoupon(coupon)}
                          className="rounded-full p-1.5 text-[var(--muted-foreground)] hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/20 dark:hover:text-red-400 transition-colors"
                        >
                          <Icon name="delete" size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {(showAddModal || editingCoupon) && (
        <CouponModal
          coupon={editingCoupon}
          onClose={() => { setShowAddModal(false); setEditingCoupon(null); }}
          onSuccess={() => {
            setShowAddModal(false);
            setEditingCoupon(null);
            utils.coupons.list.invalidate();
          }}
        />
      )}

      {deletingCoupon && (
        <DeleteConfirmModal
          coupon={deletingCoupon}
          onClose={() => setDeletingCoupon(null)}
          onSuccess={() => { setDeletingCoupon(null); utils.coupons.list.invalidate(); }}
        />
      )}
    </DashboardLayout>
  );
}

/* ─── Coupon Modal (Add / Edit) ─────────────────────── */

function toDateInputValue(iso: string) {
  return iso ? iso.slice(0, 10) : "";
}

function CouponModal({
  coupon,
  onClose,
  onSuccess,
}: {
  coupon: MappedCoupon | null;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const t = useTranslations("coupons");
  const tc = useTranslations("common");

  const isEdit = !!coupon;
  const today = new Date().toISOString().slice(0, 10);
  const defaultUntil = new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10);

  const [code, setCode] = useState(coupon?.code ?? "");
  const [name, setName] = useState(coupon?.name ?? "");
  const [type, setType] = useState(coupon?.type ?? "percentage");
  const [value, setValue] = useState(String(coupon?.value ?? ""));
  const [minOrderAmount, setMinOrderAmount] = useState(coupon?.minOrderAmount ? String(coupon.minOrderAmount / 100) : "");
  const [maxUses, setMaxUses] = useState(coupon?.maxUses ? String(coupon.maxUses) : "");
  const [validFrom, setValidFrom] = useState(coupon?.validFrom ? toDateInputValue(coupon.validFrom) : today);
  const [validUntil, setValidUntil] = useState(coupon?.validUntil ? toDateInputValue(coupon.validUntil) : defaultUntil);
  const [isActive, setIsActive] = useState(coupon?.isActive ?? true);
  const [error, setError] = useState("");

  const createMutation = trpc.coupons.create.useMutation({ onError: (err) => setError(err.message) });
  const updateMutation = trpc.coupons.update.useMutation({ onError: (err) => setError(err.message) });
  const isPending = createMutation.isPending || updateMutation.isPending;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!code.trim() || !name.trim()) { setError("Code and name are required"); return; }
    if (!value || Number(value) < 0) { setError("Value must be a positive number"); return; }

    const payload = {
      code: code.trim().toUpperCase(),
      name: name.trim(),
      type: type as typeof COUPON_TYPES[number],
      value: Number(value),
      minOrderAmount: minOrderAmount ? Math.round(Number(minOrderAmount) * 100) : undefined,
      maxUses: maxUses ? Number(maxUses) : undefined,
      validFrom: new Date(validFrom).toISOString(),
      validUntil: new Date(validUntil).toISOString(),
      isActive,
    };

    if (isEdit) {
      await updateMutation.mutateAsync({ id: coupon.id, ...payload });
    } else {
      await createMutation.mutateAsync(payload);
    }
    onSuccess();
  };

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/40" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="w-full max-w-lg rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] shadow-xl" onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center justify-between border-b border-[var(--border)] px-6 py-4">
            <h2 className="font-brand text-lg font-semibold text-[var(--foreground)]">
              {isEdit ? t("editCoupon") : t("createCoupon")}
            </h2>
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

            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <label className="font-body text-sm font-medium text-[var(--foreground)]">
                  {t("code")} <span className="text-[var(--destructive)]">*</span>
                </label>
                <input type="text" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="SUMMER20" required
                  className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-brand text-sm tracking-wider text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] placeholder:font-body placeholder:tracking-normal focus:outline-none focus:ring-2 focus:ring-[var(--ring)]" />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="font-body text-sm font-medium text-[var(--foreground)]">
                  {tc("name")} <span className="text-[var(--destructive)]">*</span>
                </label>
                <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Summer Sale" required
                  className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]" />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <label className="font-body text-sm font-medium text-[var(--foreground)]">{tc("type")}</label>
                <select value={type} onChange={(e) => setType(e.target.value)}
                  className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]">
                  {COUPON_TYPES.map((typeOption) => (
                    <option key={typeOption} value={typeOption}>{getTypeLabels(t)[typeOption]}</option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="font-body text-sm font-medium text-[var(--foreground)]">
                  {tc("value")} <span className="text-[var(--destructive)]">*</span>
                </label>
                <input type="number" min="0" step={type === "percentage" ? "1" : "0.01"} value={value} onChange={(e) => setValue(e.target.value)} placeholder={type === "percentage" ? "20" : "5.00"} required
                  className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]" />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <label className="font-body text-sm font-medium text-[var(--foreground)]">{t("minOrder")}</label>
                <input type="number" min="0" step="0.01" value={minOrderAmount} onChange={(e) => setMinOrderAmount(e.target.value)} placeholder="0.00"
                  className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]" />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="font-body text-sm font-medium text-[var(--foreground)]">{t("maxUses")}</label>
                <input type="number" min="1" step="1" value={maxUses} onChange={(e) => setMaxUses(e.target.value)} placeholder="Unlimited"
                  className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]" />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <label className="font-body text-sm font-medium text-[var(--foreground)]">{t("validFrom")}</label>
                <input type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)}
                  className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]" />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="font-body text-sm font-medium text-[var(--foreground)]">{t("validUntil")}</label>
                <input type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)}
                  className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]" />
              </div>
            </div>

            {isEdit && (
              <label className="flex items-center gap-2 cursor-pointer">
                <div
                  onClick={() => setIsActive(!isActive)}
                  className={cn(
                    "relative h-5 w-9 rounded-full transition-colors cursor-pointer",
                    isActive ? "bg-[var(--primary)]" : "bg-[var(--muted-foreground)]/30"
                  )}
                >
                  <div className={cn(
                    "absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform",
                    isActive ? "translate-x-4" : "translate-x-0.5"
                  )} />
                </div>
                <span className="font-body text-sm text-[var(--foreground)]">{tc("active")}</span>
              </label>
            )}

            <div className="flex items-center justify-end gap-3 pt-2">
              <button type="button" onClick={onClose}
                className="rounded-[var(--radius-pill)] px-4 py-2 font-brand text-sm text-[var(--foreground)] hover:bg-[var(--accent)] transition-colors">
                {tc("cancel")}
              </button>
              <button type="submit" disabled={isPending || !code.trim() || !name.trim()}
                className="flex items-center gap-2 rounded-[var(--radius-pill)] bg-[var(--primary)] px-5 py-2 font-brand text-sm font-medium text-white transition-colors hover:bg-[var(--primary)]/90 disabled:opacity-50">
                {isPending ? tc("saving") : isEdit ? t("saveChanges") : t("createCoupon")}
              </button>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}

/* ─── Delete Confirmation Modal ─────────────────────── */

function DeleteConfirmModal({
  coupon,
  onClose,
  onSuccess,
}: {
  coupon: MappedCoupon;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const t = useTranslations("coupons");
  const tc = useTranslations("common");

  const [error, setError] = useState("");
  const deleteMutation = trpc.coupons.delete.useMutation({ onError: (err) => setError(err.message) });

  const handleDelete = async () => {
    setError("");
    await deleteMutation.mutateAsync({ id: coupon.id });
    onSuccess();
  };

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/40" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="w-full max-w-sm rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] shadow-xl" onClick={(e) => e.stopPropagation()}>
          <div className="flex flex-col items-center gap-3 px-6 py-6 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30">
              <Icon name="warning" size={24} className="text-red-600 dark:text-red-400" />
            </div>
            <h3 className="font-brand text-lg font-semibold text-[var(--foreground)]">{t("deleteCoupon")}</h3>
            <p className="font-body text-sm text-[var(--muted-foreground)]">
              {t("deleteConfirm", { code: coupon.code })}
            </p>
            {error && (
              <div className="w-full rounded-[var(--radius-m)] bg-red-50 px-3 py-2 font-body text-xs text-red-600 dark:bg-red-900/20 dark:text-red-400">
                {error}
              </div>
            )}
          </div>
          <div className="flex items-center justify-end gap-3 border-t border-[var(--border)] px-6 py-4">
            <button onClick={onClose}
              className="rounded-[var(--radius-pill)] px-4 py-2 font-brand text-sm text-[var(--foreground)] hover:bg-[var(--accent)] transition-colors">
              {tc("cancel")}
            </button>
            <button onClick={handleDelete} disabled={deleteMutation.isPending}
              className="rounded-[var(--radius-pill)] bg-[var(--destructive)] px-5 py-2 font-brand text-sm font-medium text-white transition-colors hover:bg-[var(--destructive)]/90 disabled:opacity-50">
              {deleteMutation.isPending ? tc("deleting") : tc("delete")}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
