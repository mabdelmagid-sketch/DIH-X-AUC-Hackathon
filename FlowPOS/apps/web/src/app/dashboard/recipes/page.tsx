"use client";

import { useState, useMemo } from "react";
import { useTranslations } from "next-intl";
import { DashboardLayout, PageHeader } from "@/components/layout";
import { Icon } from "@/components/ui";
import { cn } from "@/lib/utils";
import { trpc } from "@/lib/trpc";

const getDifficultyLabels = (t: ReturnType<typeof useTranslations>): Record<string, string> => ({
  EASY: t("easy"),
  MEDIUM: t("medium"),
  HARD: t("hard"),
});

const DIFFICULTY_COLORS: Record<string, string> = {
  EASY: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  MEDIUM: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  HARD: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
};

export default function RecipesPage() {
  const t = useTranslations("recipes");
  const tc = useTranslations("common");
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState<"all" | "active" | "inactive">("all");

  const { data, isLoading } = trpc.recipes.list.useQuery({
    ...(activeFilter === "active" ? { isActive: true } : activeFilter === "inactive" ? { isActive: false } : {}),
    limit: 50,
  });

  const recipes = useMemo(() => {
    if (!data?.recipes) return [];
    const mapped = (data.recipes as Array<{
      id: string;
      name: string;
      description: string | null;
      yield_quantity: number;
      yield_unit: string;
      prep_time_minutes: number;
      cook_time_minutes: number;
      difficulty_level: string;
      is_active: boolean;
      category: string | null;
      product: { id: string; name: string; price: number } | null;
      created_at: string;
    }>).map((r) => ({
      id: r.id,
      name: r.name,
      description: r.description,
      yieldQuantity: r.yield_quantity,
      yieldUnit: r.yield_unit,
      prepTime: r.prep_time_minutes,
      cookTime: r.cook_time_minutes,
      totalTime: r.prep_time_minutes + r.cook_time_minutes,
      difficulty: r.difficulty_level,
      isActive: r.is_active,
      category: r.category ?? "Uncategorized",
      product: r.product?.name ?? null,
    }));

    if (!searchQuery) return mapped;
    const q = searchQuery.toLowerCase();
    return mapped.filter(
      (r) =>
        r.name.toLowerCase().includes(q) ||
        (r.description?.toLowerCase().includes(q) ?? false) ||
        r.category.toLowerCase().includes(q)
    );
  }, [data, searchQuery]);

  return (
    <DashboardLayout>
      <div className="flex flex-col gap-6">
        <PageHeader
          title={t("title")}
          description={`${data?.total ?? 0} recipes`}
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
                {filter === "all" ? tc("all") : tc(filter)}
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
        ) : recipes.length === 0 ? (
          <div className="flex h-64 items-center justify-center rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]">
            <div className="flex flex-col items-center gap-2 text-[var(--muted-foreground)]">
              <Icon name="menu_book" size={40} />
              <span className="font-body text-sm">{t("noRecipes")}</span>
            </div>
          </div>
        ) : (
          <div className="overflow-hidden rounded-[var(--radius-m)] border border-[var(--border)]">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--card)]">
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("recipe")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("category")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("product")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("yield")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("time")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{t("difficulty")}</th>
                  <th className="px-4 py-3 text-start font-brand text-[13px] font-medium text-[var(--foreground)]">{tc("status")}</th>
                </tr>
              </thead>
              <tbody>
                {recipes.map((recipe, idx) => (
                  <tr
                    key={recipe.id}
                    className={cn(
                      "bg-[var(--card)] hover:bg-[var(--accent)] transition-colors",
                      idx < recipes.length - 1 && "border-b border-[var(--border)]"
                    )}
                  >
                    <td className="px-4 py-3 font-brand text-sm font-medium text-[var(--foreground)]">
                      {recipe.name}
                    </td>
                    <td className="px-4 py-3">
                      <span className="rounded-[var(--radius-pill)] bg-[var(--secondary)] px-2.5 py-0.5 font-body text-xs text-[var(--muted-foreground)]">
                        {recipe.category}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {recipe.product ?? "\u2014"}
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {recipe.yieldQuantity} {recipe.yieldUnit}
                    </td>
                    <td className="px-4 py-3 font-body text-sm text-[var(--muted-foreground)]">
                      {recipe.totalTime > 0 ? `${recipe.totalTime} ${t("min")}` : "\u2014"}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={cn(
                          "inline-flex rounded-[var(--radius-pill)] px-2.5 py-0.5 font-body text-xs font-medium",
                          DIFFICULTY_COLORS[recipe.difficulty] ?? DIFFICULTY_COLORS.MEDIUM
                        )}
                      >
                        {getDifficultyLabels(t)[recipe.difficulty] ?? recipe.difficulty}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={cn(
                          "inline-flex rounded-[var(--radius-pill)] px-2.5 py-0.5 font-body text-xs font-medium",
                          recipe.isActive
                            ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                            : "bg-[var(--secondary)] text-[var(--muted-foreground)]"
                        )}
                      >
                        {recipe.isActive ? tc("active") : tc("inactive")}
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
