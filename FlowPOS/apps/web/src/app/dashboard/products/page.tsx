"use client";

import { useState, useMemo } from "react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { DashboardLayout, PageHeader } from "@/components/layout";
import { Icon } from "@/components/ui";
import { cn, formatCurrency } from "@/lib/utils";
import { trpc } from "@/lib/trpc";

export default function ProductsPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState<"all" | "active" | "inactive">("all");
  const [showAdd, setShowAdd] = useState(false);
  const t = useTranslations("products");
  const tc = useTranslations("common");

  const utils = trpc.useUtils();

  const { data: productsData, isLoading } = trpc.products.list.useQuery({
    limit: 100,
    ...(activeFilter === "active" ? { isActive: true } : activeFilter === "inactive" ? { isActive: false } : {}),
  });

  const { data: categoriesData } = trpc.categories.list.useQuery();

  const products = useMemo(() => {
    if (!productsData?.products) return [];
    const mapped = productsData.products.map((p: {
      id: string;
      name: string;
      price: number;
      cost: number | null;
      sku: string | null;
      is_active: boolean;
      image: string | null;
      category: { name: string } | null;
    }) => ({
      id: p.id,
      name: p.name,
      price: p.price,
      cost: p.cost,
      sku: p.sku,
      isActive: p.is_active,
      image: p.image,
      category: p.category?.name ?? t("uncategorized"),
    }));

    if (!searchQuery) return mapped;
    const q = searchQuery.toLowerCase();
    return mapped.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        p.category.toLowerCase().includes(q) ||
        (p.sku?.toLowerCase().includes(q) ?? false)
    );
  }, [productsData, searchQuery, t]);

  return (
    <DashboardLayout>
      <div className="flex flex-col gap-6">
        <PageHeader
          title={t("title")}
          description={`${productsData?.total ?? 0} ${t("description")}`}
          actions={
            <button
              onClick={() => setShowAdd(true)}
              className="flex items-center gap-2 rounded-[var(--radius-pill)] bg-[var(--primary)] px-4 py-2 font-brand text-sm font-medium text-white transition-colors hover:bg-[var(--primary)]/90"
            >
              <Icon name="add" size={18} />
              {t("addProduct")}
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
                  "rounded-[var(--radius-pill)] px-3 py-1.5 font-body text-xs transition-colors",
                  activeFilter === filter
                    ? "bg-[var(--primary)] font-medium text-white"
                    : "bg-[var(--secondary)] text-[var(--muted-foreground)] hover:bg-[var(--accent)]"
                )}
              >
                {tc(filter)}
              </button>
            ))}
          </div>
        </div>

        {/* Products Table */}
        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
              <span className="font-body text-sm text-[var(--muted-foreground)]">{t("loading")}</span>
            </div>
          </div>
        ) : products.length === 0 ? (
          <div className="flex h-64 items-center justify-center rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]">
            <div className="flex flex-col items-center gap-2 text-[var(--muted-foreground)]">
              <Icon name="inventory_2" size={40} />
              <span className="font-body text-sm">{t("noProducts")}</span>
              <span className="font-body text-xs">{t("addFirstProduct")}</span>
            </div>
          </div>
        ) : (
          <div className="overflow-hidden rounded-[var(--radius-m)] border border-[var(--border)]">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--card)]">
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("product")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("category")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("sku")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("price")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("cost")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("status")}</th>
                </tr>
              </thead>
              <tbody>
                {products.map((product, idx) => (
                  <tr
                    key={product.id}
                    className={cn(
                      "bg-[var(--card)] hover:bg-[var(--accent)] transition-colors cursor-pointer",
                      idx < products.length - 1 && "border-b border-[var(--border)]"
                    )}
                  >
                    <td className="px-4 py-3">
                      <span className="font-brand text-sm font-medium text-[var(--foreground)]">
                        {product.name}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="rounded-[var(--radius-pill)] bg-[var(--secondary)] px-2.5 py-0.5 font-body text-xs text-[var(--muted-foreground)]">
                        {product.category}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {product.sku ?? "\u2014"}
                    </td>
                    <td className="px-4 py-3 font-brand text-sm font-medium text-[var(--foreground)]">
                      {formatCurrency(product.price)}
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {product.cost ? formatCurrency(product.cost) : "\u2014"}
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn(
                        "inline-flex rounded-[var(--radius-pill)] px-2.5 py-0.5 font-body text-xs font-medium",
                        product.isActive
                          ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                          : "bg-[var(--secondary)] text-[var(--muted-foreground)]"
                      )}>
                        {product.isActive ? tc("active") : tc("inactive")}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add Product Modal */}
      {showAdd && (
        <AddProductModal
          categories={categoriesData ?? []}
          onClose={() => setShowAdd(false)}
          onSuccess={() => {
            setShowAdd(false);
            utils.products.list.invalidate();
          }}
        />
      )}
    </DashboardLayout>
  );
}

/* ------------------------------------------------------------------ */
/*  Types                                                               */
/* ------------------------------------------------------------------ */

type IngredientRow = {
  ingredientId: string;
  name: string;
  quantity: string;
  unit: string;
};

type AvailableIngredient = {
  id: string;
  name: string;
  unit: string;
  category: string;
  cost_per_unit: number;
};

/* ------------------------------------------------------------------ */
/*  Add Product Modal                                                  */
/* ------------------------------------------------------------------ */

function AddProductModal({
  categories,
  onClose,
  onSuccess,
}: {
  categories: Array<{ id: string; name: string }>;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const t = useTranslations("products");
  const tc = useTranslations("common");

  // Product fields
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const [cost, setCost] = useState("");
  const [sku, setSku] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [error, setError] = useState("");

  // Ingredients section
  const [showIngredients, setShowIngredients] = useState(false);
  const [ingredientRows, setIngredientRows] = useState<IngredientRow[]>([]);
  const [aiLoading, setAiLoading] = useState(false);

  // Fetch available ingredients from DB
  const { data: ingredientsData } = trpc.ingredients.list.useQuery(
    { limit: 100, isActive: true },
    { enabled: showIngredients }
  );

  const availableIngredients: AvailableIngredient[] = useMemo(() => {
    if (!ingredientsData?.ingredients) return [];
    return ingredientsData.ingredients.map((i) => ({
      id: i.id,
      name: i.name,
      unit: i.unit,
      category: i.category,
      cost_per_unit: i.cost_per_unit,
    }));
  }, [ingredientsData]);

  // Mutations
  const createProduct = trpc.products.create.useMutation({
    onError: (err) => setError(err.message),
  });

  const createRecipe = trpc.recipes.create.useMutation({
    onError: (err) => setError(err.message),
  });

  const addIngredientRow = () => {
    setIngredientRows((prev) => [
      ...prev,
      { ingredientId: "", name: "", quantity: "", unit: "g" },
    ]);
  };

  const removeIngredientRow = (index: number) => {
    setIngredientRows((prev) => prev.filter((_, i) => i !== index));
  };

  const updateIngredientRow = (index: number, updates: Partial<IngredientRow>) => {
    setIngredientRows((prev) =>
      prev.map((row, i) => {
        if (i !== index) return row;
        const updated = { ...row, ...updates };
        // When ingredient is selected, auto-fill the unit
        if (updates.ingredientId && updates.ingredientId !== row.ingredientId) {
          const ing = availableIngredients.find((a) => a.id === updates.ingredientId);
          if (ing) {
            updated.name = ing.name;
            updated.unit = ing.unit;
          }
        }
        return updated;
      })
    );
  };

  /* ---- AI Suggest ---- */
  const handleAiSuggest = async () => {
    if (!name.trim()) {
      setError(t("aiNeedName"));
      return;
    }

    setAiLoading(true);
    setError("");

    try {
      const res = await fetch("/api/ai/suggest-ingredients", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          productName: name.trim(),
          existingIngredients: availableIngredients.map((i) => ({
            id: i.id,
            name: i.name,
            unit: i.unit,
          })),
        }),
      });

      if (!res.ok) {
        throw new Error("AI suggestion failed");
      }

      const data = await res.json();
      const suggestions: Array<{ name: string; quantity: number; unit: string }> = data.suggestions ?? [];

      if (suggestions.length === 0) {
        setError(t("aiNoMatch"));
        return;
      }

      // Match suggestions to available ingredients
      const newRows: IngredientRow[] = [];
      for (const s of suggestions) {
        const match = availableIngredients.find(
          (a) => a.name.toLowerCase() === s.name.toLowerCase()
        );
        if (match) {
          // Skip if already added
          if (ingredientRows.some((r) => r.ingredientId === match.id)) continue;
          newRows.push({
            ingredientId: match.id,
            name: match.name,
            quantity: String(s.quantity),
            unit: s.unit,
          });
        }
      }

      if (newRows.length === 0) {
        setError(t("aiNoInventoryMatch"));
        return;
      }

      setIngredientRows((prev) => [...prev, ...newRows]);
    } catch {
      setError(t("aiFailed"));
    } finally {
      setAiLoading(false);
    }
  };

  /* ---- Submit ---- */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!name.trim()) {
      setError(t("nameRequired"));
      return;
    }

    const priceNum = Math.round(parseFloat(price) * 100);
    if (isNaN(priceNum) || priceNum < 0) {
      setError(t("invalidPrice"));
      return;
    }

    const costNum = cost ? Math.round(parseFloat(cost) * 100) : null;

    // Validate ingredient rows if any
    const validIngredients = ingredientRows.filter(
      (r) => r.ingredientId && r.quantity && parseFloat(r.quantity) > 0
    );

    try {
      // Step 1: Create the product
      const product = await createProduct.mutateAsync({
        name: name.trim(),
        price: priceNum,
        cost: costNum,
        sku: sku.trim() || null,
        categoryId: categoryId || null,
        isActive,
      });

      // Step 2: If there are ingredients, create a recipe linking them
      if (validIngredients.length > 0 && product?.id) {
        const recipe = await createRecipe.mutateAsync({
          name: `${name.trim()} Recipe`,
          productId: product.id,
          ingredients: validIngredients.map((r, idx) => ({
            ingredientId: r.ingredientId,
            quantity: parseFloat(r.quantity),
            unit: r.unit as "g" | "kg" | "mg" | "ml" | "l" | "cl" | "oz" | "lb" | "fl_oz" | "cup" | "tbsp" | "tsp" | "piece" | "each" | "slice" | "portion" | "serving",
            sortOrder: idx,
          })),
        });

        // Step 3: Auto-embed the recipe for future similarity search (fire & forget)
        if (recipe?.id) {
          fetch("/api/ai/embed-recipe", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ recipeId: recipe.id }),
          }).catch(() => {}); // Non-blocking
        }
      }

      onSuccess();
    } catch {
      // Error already set by mutation onError
    }
  };

  const isPending = createProduct.isPending || createRecipe.isPending;

  const UNITS = [
    "g", "kg", "mg", "ml", "l", "cl", "oz", "lb", "fl_oz",
    "cup", "tbsp", "tsp", "piece", "each", "slice", "portion", "serving",
  ];

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-40 bg-black/40" onClick={onClose} />

      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <form
          onSubmit={handleSubmit}
          className="w-full max-w-lg max-h-[90vh] flex flex-col rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] shadow-xl"
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-[var(--border)] px-6 py-4">
            <h2 className="font-brand text-lg font-semibold text-[var(--foreground)]">
              {t("addProduct")}
            </h2>
            <button
              type="button"
              onClick={onClose}
              className="flex h-8 w-8 items-center justify-center rounded-full hover:bg-[var(--accent)] transition-colors"
            >
              <Icon name="close" size={18} className="text-[var(--foreground)]" />
            </button>
          </div>

          {/* Body - scrollable */}
          <div className="flex flex-col gap-4 p-6 overflow-y-auto">
            {error && (
              <div className="rounded-[var(--radius-m)] bg-red-50 px-4 py-2 font-body text-sm text-red-700 dark:bg-red-900/20 dark:text-red-400">
                {error}
              </div>
            )}

            {/* Name */}
            <div className="flex flex-col gap-1.5">
              <label className="font-body text-sm font-medium text-[var(--foreground)]">
                {tc("name")} *
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("namePlaceholder")}
                className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--ring)]"
              />
            </div>

            {/* Price + Cost */}
            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-1.5">
                <label className="font-body text-sm font-medium text-[var(--foreground)]">
                  {tc("price")} *
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={price}
                  onChange={(e) => setPrice(e.target.value)}
                  placeholder="0.00"
                  className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--ring)]"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="font-body text-sm font-medium text-[var(--foreground)]">
                  {t("cost")}
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={cost}
                  onChange={(e) => setCost(e.target.value)}
                  placeholder="0.00"
                  className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--ring)]"
                />
              </div>
            </div>

            {/* Category */}
            <div className="flex flex-col gap-1.5">
              <label className="font-body text-sm font-medium text-[var(--foreground)]">
                {t("category")}
              </label>
              <select
                value={categoryId}
                onChange={(e) => setCategoryId(e.target.value)}
                className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--ring)]"
              >
                <option value="">{t("noCategory")}</option>
                {categories.map((cat) => (
                  <option key={cat.id} value={cat.id}>
                    {cat.name}
                  </option>
                ))}
              </select>
            </div>

            {/* SKU */}
            <div className="flex flex-col gap-1.5">
              <label className="font-body text-sm font-medium text-[var(--foreground)]">
                {t("sku")}
              </label>
              <input
                type="text"
                value={sku}
                onChange={(e) => setSku(e.target.value)}
                placeholder={t("sku")}
                className="h-10 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-3 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--ring)]"
              />
            </div>

            {/* Active toggle */}
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
                className="h-4 w-4 rounded border-[var(--input)] accent-[var(--primary)]"
              />
              <span className="font-body text-sm text-[var(--foreground)]">{t("activeOnPos")}</span>
            </label>

            {/* ---- Ingredients Section ---- */}
            <div className="border-t border-[var(--border)] pt-4">
              <button
                type="button"
                onClick={() => {
                  setShowIngredients(!showIngredients);
                  if (!showIngredients && ingredientRows.length === 0) {
                    addIngredientRow();
                  }
                }}
                className="flex w-full items-center justify-between rounded-[var(--radius-m)] px-3 py-2 font-body text-sm font-medium text-[var(--foreground)] hover:bg-[var(--accent)] transition-colors"
              >
                <div className="flex items-center gap-2">
                  <Icon name="restaurant" size={18} className="text-[var(--primary)]" />
                  <span>{t("ingredients")} {ingredientRows.length > 0 ? `(${ingredientRows.length})` : ""}</span>
                </div>
                <Icon
                  name={showIngredients ? "expand_less" : "expand_more"}
                  size={20}
                  className="text-[var(--muted-foreground)]"
                />
              </button>

              {showIngredients && (
                <div className="mt-3 flex flex-col gap-3">
                  {/* No ingredients — prompt to add them first */}
                  {availableIngredients.length === 0 && !ingredientsData ? (
                    <div className="flex items-center justify-center py-2">
                      <div className="h-5 w-5 animate-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
                    </div>
                  ) : availableIngredients.length === 0 ? (
                    <div className="flex flex-col items-center gap-3 rounded-[var(--radius-m)] border border-dashed border-[var(--border)] bg-[var(--background)] px-4 py-6">
                      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-amber-100 dark:bg-amber-900/30">
                        <Icon name="egg_alt" size={24} className="text-amber-600 dark:text-amber-400" />
                      </div>
                      <div className="text-center">
                        <p className="font-body text-sm font-medium text-[var(--foreground)]">
                          {t("noIngredients")}
                        </p>
                        <p className="mt-1 font-body text-xs text-[var(--muted-foreground)]">
                          {t("addIngredientsFirst")}
                        </p>
                      </div>
                      <Link
                        href="/dashboard/ingredients"
                        className="flex items-center gap-2 rounded-[var(--radius-pill)] bg-[var(--primary)] px-4 py-2 font-brand text-sm font-medium text-white transition-colors hover:bg-[var(--primary)]/90"
                      >
                        <Icon name="add" size={16} />
                        {t("goToIngredients")}
                      </Link>
                    </div>
                  ) : (
                    <>
                      {/* AI Suggest button */}
                      <button
                        type="button"
                        onClick={handleAiSuggest}
                        disabled={aiLoading || !name.trim()}
                        className="flex items-center justify-center gap-2 rounded-[var(--radius-m)] border border-dashed border-[var(--primary)] px-3 py-2 font-body text-sm text-[var(--primary)] transition-colors hover:bg-[var(--primary)]/5 disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        {aiLoading ? (
                          <>
                            <div className="h-4 w-4 animate-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
                            {t("suggesting")}
                          </>
                        ) : (
                          <>
                            <Icon name="auto_awesome" size={16} />
                            {t("suggestAI")}
                          </>
                        )}
                      </button>

                      {/* Ingredient rows */}
                      {ingredientRows.map((row, idx) => (
                        <div key={idx} className="flex items-end gap-2">
                          {/* Ingredient select */}
                          <div className="flex flex-1 flex-col gap-1">
                            {idx === 0 && (
                              <label className="font-body text-xs text-[var(--muted-foreground)]">{t("ingredientLabel")}</label>
                            )}
                            <select
                              value={row.ingredientId}
                              onChange={(e) =>
                                updateIngredientRow(idx, { ingredientId: e.target.value })
                              }
                              className="h-9 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-2 font-body text-sm text-[var(--foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--ring)]"
                            >
                              <option value="">{t("selectIngredient")}</option>
                              {availableIngredients.map((ing) => (
                                <option key={ing.id} value={ing.id}>
                                  {ing.name}
                                </option>
                              ))}
                            </select>
                          </div>

                          {/* Quantity */}
                          <div className="flex w-20 flex-col gap-1">
                            {idx === 0 && (
                              <label className="font-body text-xs text-[var(--muted-foreground)]">{t("qty")}</label>
                            )}
                            <input
                              type="number"
                              step="0.1"
                              min="0"
                              value={row.quantity}
                              onChange={(e) =>
                                updateIngredientRow(idx, { quantity: e.target.value })
                              }
                              placeholder="0"
                              className="h-9 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-2 font-body text-sm text-[var(--foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--ring)]"
                            />
                          </div>

                          {/* Unit */}
                          <div className="flex w-20 flex-col gap-1">
                            {idx === 0 && (
                              <label className="font-body text-xs text-[var(--muted-foreground)]">{t("unitLabel")}</label>
                            )}
                            <select
                              value={row.unit}
                              onChange={(e) =>
                                updateIngredientRow(idx, { unit: e.target.value })
                              }
                              className="h-9 rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] px-2 font-body text-sm text-[var(--foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--ring)]"
                            >
                              {UNITS.map((u) => (
                                <option key={u} value={u}>
                                  {u}
                                </option>
                              ))}
                            </select>
                          </div>

                          {/* Remove */}
                          <button
                            type="button"
                            onClick={() => removeIngredientRow(idx)}
                            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[var(--muted-foreground)] hover:bg-red-50 hover:text-red-600 transition-colors dark:hover:bg-red-900/20"
                          >
                            <Icon name="close" size={16} />
                          </button>
                        </div>
                      ))}

                      {/* Add row button */}
                      <button
                        type="button"
                        onClick={addIngredientRow}
                        className="flex items-center gap-1.5 rounded-[var(--radius-m)] px-3 py-1.5 font-body text-xs text-[var(--primary)] hover:bg-[var(--accent)] transition-colors"
                      >
                        <Icon name="add" size={14} />
                        {t("addIngredientRow")}
                      </button>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-3 border-t border-[var(--border)] px-6 py-4">
            <button
              type="button"
              onClick={onClose}
              className="rounded-[var(--radius-pill)] px-4 py-2 font-brand text-sm text-[var(--foreground)] hover:bg-[var(--accent)] transition-colors"
            >
              {tc("cancel")}
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="flex items-center gap-2 rounded-[var(--radius-pill)] bg-[var(--primary)] px-5 py-2 font-brand text-sm font-medium text-white transition-colors hover:bg-[var(--primary)]/90 disabled:opacity-50"
            >
              {isPending ? tc("creating") : t("createProduct")}
            </button>
          </div>
        </form>
      </div>
    </>
  );
}
