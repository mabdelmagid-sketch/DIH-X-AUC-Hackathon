"use client";

import { useState, useMemo } from "react";
import { useTranslations } from "next-intl";
import { DashboardLayout, PageHeader } from "@/components/layout";
import { Icon } from "@/components/ui";
import { cn, formatCurrency } from "@/lib/utils";
import { trpc } from "@/lib/trpc";

const CATEGORIES = [
  "DAIRY", "MEAT", "SEAFOOD", "PRODUCE", "GRAINS", "SPICES",
  "BEVERAGES", "OILS", "SAUCES", "BAKING", "FROZEN", "CANNED",
  "DRY_GOODS", "PACKAGING", "CLEANING", "OTHER",
] as const;

const UNITS = [
  "g", "kg", "mg", "ml", "l", "cl", "oz", "lb", "fl_oz",
  "cup", "tbsp", "tsp", "piece", "each", "slice", "portion", "serving",
] as const;

const CATEGORY_LABELS: Record<string, string> = {
  DAIRY: "Dairy", MEAT: "Meat", SEAFOOD: "Seafood", PRODUCE: "Produce",
  GRAINS: "Grains", SPICES: "Spices", BEVERAGES: "Beverages", OILS: "Oils",
  SAUCES: "Sauces", BAKING: "Baking", FROZEN: "Frozen", CANNED: "Canned",
  DRY_GOODS: "Dry Goods", PACKAGING: "Packaging", CLEANING: "Cleaning", OTHER: "Other",
};

type MappedIngredient = {
  id: string;
  name: string;
  sku: string | null;
  category: string;
  unit: string;
  costPerUnit: number;
  minStockLevel: number;
  currentStock: number;
  isActive: boolean;
  isLowStock: boolean;
  supplierId: string | null;
  supplier: string | null;
};

export default function IngredientsPage() {
  const t = useTranslations("ingredients");
  const tc = useTranslations("common");
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState<"all" | "active" | "low_stock">("all");
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingIngredient, setEditingIngredient] = useState<MappedIngredient | null>(null);
  const [deletingIngredient, setDeletingIngredient] = useState<MappedIngredient | null>(null);

  const utils = trpc.useUtils();
  const { data, isLoading } = trpc.ingredients.list.useQuery({
    ...(activeFilter === "active" ? { isActive: true } : activeFilter === "low_stock" ? { lowStockOnly: true } : {}),
    limit: 50,
  });

  const ingredients = useMemo(() => {
    if (!data?.ingredients) return [];
    const mapped: MappedIngredient[] = (data.ingredients as Array<{
      id: string;
      name: string;
      sku: string | null;
      category: string;
      unit: string;
      cost_per_unit: number;
      min_stock_level: number;
      is_active: boolean;
      currentStock: number;
      supplier: { id: string; name: string | null } | null;
    }>).map((i) => ({
      id: i.id,
      name: i.name,
      sku: i.sku,
      category: i.category,
      unit: i.unit,
      costPerUnit: i.cost_per_unit,
      minStockLevel: i.min_stock_level,
      currentStock: i.currentStock ?? 0,
      isActive: i.is_active,
      isLowStock: (i.currentStock ?? 0) <= i.min_stock_level && i.min_stock_level > 0,
      supplierId: i.supplier?.id ?? null,
      supplier: i.supplier?.name ?? null,
    }));

    if (!searchQuery) return mapped;
    const q = searchQuery.toLowerCase();
    return mapped.filter(
      (i) =>
        i.name.toLowerCase().includes(q) ||
        (i.sku?.toLowerCase().includes(q) ?? false) ||
        (i.supplier?.toLowerCase().includes(q) ?? false) ||
        i.category.toLowerCase().includes(q)
    );
  }, [data, searchQuery]);

  return (
    <DashboardLayout>
      <div className="flex flex-col gap-6">
        <PageHeader
          title={t("title")}
          description={`${data?.total ?? 0} ingredients`}
          actions={
            <button
              onClick={() => setShowAddModal(true)}
              className="flex items-center gap-2 rounded-[var(--radius-pill)] bg-[var(--primary)] px-4 py-2 font-brand text-sm font-medium text-white transition-colors hover:bg-[var(--primary)]/90"
            >
              <Icon name="add" size={18} />
              {t("addIngredient")}
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
              { key: "all" as const, label: "All" },
              { key: "active" as const, label: "Active" },
              { key: "low_stock" as const, label: "Low Stock" },
            ]).map((filter) => (
              <button
                key={filter.key}
                onClick={() => setActiveFilter(filter.key)}
                className={cn(
                  "rounded-[var(--radius-pill)] px-3 py-1.5 font-body text-xs transition-colors",
                  activeFilter === filter.key
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
        ) : ingredients.length === 0 ? (
          <div className="flex h-64 items-center justify-center rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]">
            <div className="flex flex-col items-center gap-2 text-[var(--muted-foreground)]">
              <Icon name="egg" size={40} />
              <span className="font-body text-sm">{t("noIngredients")}</span>
            </div>
          </div>
        ) : (
          <div className="overflow-hidden rounded-[var(--radius-m)] border border-[var(--border)]">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--card)]">
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("ingredient")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">Category</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("unit")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("costPerUnit")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("stock")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("supplier")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">Status</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">Actions</th>
                </tr>
              </thead>
              <tbody>
                {ingredients.map((ingredient, idx) => (
                  <tr
                    key={ingredient.id}
                    className={cn(
                      "bg-[var(--card)] hover:bg-[var(--accent)] transition-colors",
                      idx < ingredients.length - 1 && "border-b border-[var(--border)]"
                    )}
                  >
                    <td className="px-4 py-3 font-brand text-sm font-medium text-[var(--foreground)]">
                      {ingredient.name}
                    </td>
                    <td className="px-4 py-3">
                      <span className="rounded-[var(--radius-pill)] bg-[var(--secondary)] px-2.5 py-0.5 font-body text-xs text-[var(--muted-foreground)]">
                        {CATEGORY_LABELS[ingredient.category] ?? ingredient.category}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {ingredient.unit}
                    </td>
                    <td className="px-4 py-3 font-brand text-sm font-medium text-[var(--foreground)]">
                      {formatCurrency(ingredient.costPerUnit)}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={cn(
                          "font-brand text-sm font-medium",
                          ingredient.isLowStock
                            ? "text-amber-600 dark:text-amber-400"
                            : ingredient.currentStock === 0
                              ? "text-red-600 dark:text-red-400"
                              : "text-[var(--foreground)]"
                        )}
                      >
                        {ingredient.currentStock}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {ingredient.supplier ?? "\u2014"}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={cn(
                          "inline-flex rounded-[var(--radius-pill)] px-2.5 py-0.5 font-body text-xs font-medium",
                          ingredient.isActive
                            ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                            : "bg-[var(--secondary)] text-[var(--muted-foreground)]"
                        )}
                      >
                        {ingredient.isActive                       ? t("active")
                      : t("inactive")}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => setEditingIngredient(ingredient)}
                          className="rounded-full p-1.5 text-[var(--muted-foreground)] hover:bg-[var(--accent)] hover:text-[var(--foreground)] transition-colors"
                        >
                          <Icon name="edit" size={16} />
                        </button>
                        <button
                          onClick={() => setDeletingIngredient(ingredient)}
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

      {(showAddModal || editingIngredient) && (
        <IngredientModal
          ingredient={editingIngredient}
          onClose={() => { setShowAddModal(false); setEditingIngredient(null); }}
          onSuccess={() => {
            setShowAddModal(false);
            setEditingIngredient(null);
            utils.ingredients.list.invalidate();
          }}
        />
      )}

      {deletingIngredient && (
        <DeleteConfirmModal
          ingredient={deletingIngredient}
          onClose={() => setDeletingIngredient(null)}
          onSuccess={() => { setDeletingIngredient(null); utils.ingredients.list.invalidate(); }}
        />
      )}
    </DashboardLayout>
  );
}

/* ─── Ingredient Modal (Add / Edit) ─────────────────── */

function IngredientModal({
  ingredient,
  onClose,
  onSuccess,
}: {
  ingredient: MappedIngredient | null;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const t = useTranslations("ingredients");
  const tc = useTranslations("common");
  const isEdit = !!ingredient;
  const [name, setName] = useState(ingredient?.name ?? "");
  const [sku, setSku] = useState(ingredient?.sku ?? "");
  const [category, setCategory] = useState(ingredient?.category ?? "OTHER");
  const [unit, setUnit] = useState(ingredient?.unit ?? "each");
  const [costPerUnit, setCostPerUnit] = useState(ingredient ? String(ingredient.costPerUnit / 100) : "");
  const [minStockLevel, setMinStockLevel] = useState(String(ingredient?.minStockLevel ?? "0"));
  const [supplierId, setSupplierId] = useState(ingredient?.supplierId ?? "");
  const [isActive, setIsActive] = useState(ingredient?.isActive ?? true);
  const [error, setError] = useState("");

  const { data: supplierData } = trpc.suppliers.list.useQuery({ limit: 100 });
  const suppliers = (supplierData?.suppliers ?? []) as Array<{ id: string; name: string }>;

  const createMutation = trpc.ingredients.create.useMutation({ onError: (err) => setError(err.message) });
  const updateMutation = trpc.ingredients.update.useMutation({ onError: (err) => setError(err.message) });
  const isPending = createMutation.isPending || updateMutation.isPending;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!name.trim()) { setError("Ingredient name is required"); return; }

    const payload = {
      name: name.trim(),
      sku: sku.trim() || undefined,
      category: category as typeof CATEGORIES[number],
      unit: unit as typeof UNITS[number],
      costPerUnit: costPerUnit ? Math.round(Number(costPerUnit) * 100) : 0,
      minStockLevel: Number(minStockLevel) || 0,
      supplierId: supplierId || undefined,
      isActive,
    };

    if (isEdit) {
      await updateMutation.mutateAsync({ id: ingredient.id, ...payload });
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
              {isEdit ? t("editIngredient") : t("addIngredient")}
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
                  Name <span className="text-[var(--destructive)]">*</span>
                </label>
                <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder={t("ingredientName")} required
                  className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]" />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="font-body text-sm font-medium text-[var(--foreground)]">SKU</label>
                <input type="text" value={sku} onChange={(e) => setSku(e.target.value)} placeholder={t("optionalSku")}
                  className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]" />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <label className="font-body text-sm font-medium text-[var(--foreground)]">Category</label>
                <select value={category} onChange={(e) => setCategory(e.target.value)}
                  className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]">
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c}>{CATEGORY_LABELS[c]}</option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="font-body text-sm font-medium text-[var(--foreground)]">Unit</label>
                <select value={unit} onChange={(e) => setUnit(e.target.value)}
                  className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]">
                  {UNITS.map((u) => (
                    <option key={u} value={u}>{u}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <label className="font-body text-sm font-medium text-[var(--foreground)]">Cost per Unit ($)</label>
                <input type="number" step="0.01" min="0" value={costPerUnit} onChange={(e) => setCostPerUnit(e.target.value)} placeholder="0.00"
                  className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]" />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="font-body text-sm font-medium text-[var(--foreground)]">{t("minStockLevel")}</label>
                <input type="number" step="1" min="0" value={minStockLevel} onChange={(e) => setMinStockLevel(e.target.value)} placeholder="0"
                  className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]" />
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="font-body text-sm font-medium text-[var(--foreground)]">Supplier</label>
              <select value={supplierId} onChange={(e) => setSupplierId(e.target.value)}
                className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)]">
                <option value="">{t("noSupplier")}</option>
                {suppliers.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
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
                <span className="font-body text-sm text-[var(--foreground)]">Active</span>
              </label>
            )}

            <div className="flex items-center justify-end gap-3 pt-2">
              <button type="button" onClick={onClose}
                className="rounded-[var(--radius-pill)] px-4 py-2 font-brand text-sm text-[var(--foreground)] hover:bg-[var(--accent)] transition-colors">
                {tc("cancel")}
              </button>
              <button type="submit" disabled={isPending || !name.trim()}
                className="flex items-center gap-2 rounded-[var(--radius-pill)] bg-[var(--primary)] px-5 py-2 font-brand text-sm font-medium text-white transition-colors hover:bg-[var(--primary)]/90 disabled:opacity-50">
                {isPending ? tc("saving") : isEdit ? tc("save") : t("addIngredient")}
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
  ingredient,
  onClose,
  onSuccess,
}: {
  ingredient: MappedIngredient;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const t = useTranslations("ingredients");
  const tc = useTranslations("common");
  const [error, setError] = useState("");
  const deleteMutation = trpc.ingredients.delete.useMutation({ onError: (err) => setError(err.message) });

  const handleDelete = async () => {
    setError("");
    await deleteMutation.mutateAsync({ id: ingredient.id });
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
            <h3 className="font-brand text-lg font-semibold text-[var(--foreground)]">{t("deleteIngredient")}</h3>
            <p className="font-body text-sm text-[var(--muted-foreground)]">
              {t("deleteConfirm", { name: ingredient.name })}
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
