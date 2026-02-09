"use client";

import { useTranslations } from "next-intl";
import { Icon } from "@/components/ui";
import { cn } from "@/lib/utils";
import { trpc } from "@/lib/trpc";
import { useAuthStore } from "@/store/auth-store";

export function ExpirySuggestions() {
  const t = useTranslations("dashboard");
  const locationId = useAuthStore((s) => s.locationId);

  const { data: suggestions, isLoading } =
    trpc.recipes.getSuggestionsForExpiring.useQuery(
      { locationId: locationId!, daysThreshold: 7 },
      { enabled: !!locationId, refetchInterval: 60_000 }
    );

  if (isLoading) {
    return (
      <div className="flex h-32 animate-pulse items-center justify-center rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]" />
    );
  }

  if (!suggestions || suggestions.length === 0) {
    return null; // Don't show section if nothing is expiring
  }

  return (
    <div className="flex flex-col rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-[var(--border)] px-6 py-4">
        <Icon name="schedule" size={20} className="text-amber-500" />
        <span className="font-brand text-base font-semibold text-[var(--foreground)]">
          {t("useBeforeExpires")}
        </span>
        <span className="rounded-[var(--radius-pill)] bg-amber-100 px-2 py-0.5 font-body text-xs font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
          {t("suggestions", { count: suggestions.length })}
        </span>
      </div>

      {/* Suggestions */}
      <div className="flex flex-col divide-y divide-[var(--border)]">
        {suggestions.slice(0, 5).map((suggestion) => {
          const recipe = suggestion.recipe as {
            id: string;
            name: string;
            product?: { name: string; price: number } | null;
          };
          const urgency = suggestion.urgency as number;
          const maxServings = suggestion.maxServingsFromExpiring as number;
          const expiringIngredients = suggestion.expiringIngredientsUsed as Array<{
            ingredientName: string;
            daysUntilExpiry: number;
            quantityExpiring: number;
            quantityNeeded: number;
            unit: string;
          }>;

          return (
            <div key={recipe.id} className="flex items-start gap-4 px-6 py-4">
              {/* Urgency indicator */}
              <div
                className={cn(
                  "mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full font-brand text-sm font-bold",
                  urgency <= 1
                    ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                    : urgency <= 3
                      ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
                      : "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400"
                )}
              >
                {urgency}d
              </div>

              {/* Content */}
              <div className="flex flex-1 flex-col gap-1">
                <div className="flex items-center gap-2">
                  <span className="font-brand text-sm font-semibold text-[var(--foreground)]">
                    {recipe.product?.name ?? recipe.name}
                  </span>
                  {maxServings > 0 && (
                    <span className="rounded-[var(--radius-pill)] bg-green-100 px-2 py-0.5 font-body text-[11px] font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400">
                      {t("canMake", { count: maxServings })}
                    </span>
                  )}
                </div>

                {/* Expiring ingredients */}
                <div className="flex flex-wrap gap-1.5">
                  {expiringIngredients.map((ing) => (
                    <span
                      key={ing.ingredientName}
                      className={cn(
                        "inline-flex items-center gap-1 rounded-[var(--radius-pill)] px-2 py-0.5 font-body text-[11px]",
                        ing.daysUntilExpiry <= 1
                          ? "bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400"
                          : "bg-amber-50 text-amber-600 dark:bg-amber-900/20 dark:text-amber-400"
                      )}
                    >
                      {ing.ingredientName}
                      <span className="font-medium">
                        {ing.daysUntilExpiry <= 0
                          ? t("expired")
                          : t("daysLeft", { days: ing.daysUntilExpiry })}
                      </span>
                    </span>
                  ))}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
