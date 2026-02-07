"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { DashboardLayout, PageHeader } from "@/components/layout";
import { getForecast } from "@/lib/forecasting-api";

export default function ForecastPage() {
  const t = useTranslations("forecast");

  const [forecasts, setForecasts] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(false);
  const [daysAhead, setDaysAhead] = useState(7);
  const [itemFilter, setItemFilter] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleForecast() {
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const result = await getForecast(daysAhead, itemFilter || undefined);
      setForecasts(result.forecasts);
      setMessage(
        `Generated ${result.forecasts.length} forecasts at ${new Date(result.generated_at).toLocaleString()}`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Forecast failed");
    } finally {
      setLoading(false);
    }
  }

  // Group forecasts by item
  const byItem: Record<string, Record<string, unknown>[]> = {};
  for (const f of forecasts) {
    const item = String(f.item_title || "Unknown");
    if (!byItem[item]) byItem[item] = [];
    byItem[item].push(f);
  }

  return (
    <DashboardLayout>
      <div className="flex flex-col gap-6">
        <PageHeader title={t("title")} description={t("description")} />

        {/* Alerts */}
        {error && (
          <div className="rounded-[var(--radius-m)] border border-[var(--destructive)] bg-[var(--destructive)]/10 px-4 py-3 font-body text-sm text-[var(--destructive)]">
            {error}
          </div>
        )}
        {message && (
          <div className="rounded-[var(--radius-m)] border border-[var(--primary)] bg-[var(--primary)]/10 px-4 py-3 font-body text-sm text-[var(--primary)]">
            {message}
          </div>
        )}

        {/* Controls */}
        <div className="flex flex-wrap items-end gap-4 rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] p-6">
          <div>
            <label className="mb-1 block font-body text-xs font-medium text-[var(--muted-foreground)]">
              {t("daysAhead")}
            </label>
            <select
              value={daysAhead}
              onChange={(e) => setDaysAhead(Number(e.target.value))}
              className="rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--background)] px-3 py-2 font-body text-sm text-[var(--foreground)]"
            >
              <option value={7}>7 days</option>
              <option value={14}>14 days</option>
              <option value={30}>30 days</option>
            </select>
          </div>

          <div>
            <label className="mb-1 block font-body text-xs font-medium text-[var(--muted-foreground)]">
              {t("itemFilter")}
            </label>
            <input
              value={itemFilter}
              onChange={(e) => setItemFilter(e.target.value)}
              placeholder="e.g. Coffee"
              className="w-48 rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--background)] px-3 py-2 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)]"
            />
          </div>

          <button
            onClick={handleForecast}
            disabled={loading}
            className="rounded-[var(--radius-pill)] bg-[var(--primary)] px-6 py-2 font-body text-sm font-medium text-white transition-colors hover:opacity-90 disabled:opacity-50"
          >
            {loading ? t("generating") : t("generate")}
          </button>
        </div>

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-12">
            <span className="animate-pulse font-body text-sm text-[var(--muted-foreground)]">
              {t("generating")}
            </span>
          </div>
        )}

        {/* Results */}
        {Object.keys(byItem).length > 0 && (
          <div className="flex flex-col gap-4">
            {Object.entries(byItem)
              .slice(0, 20)
              .map(([item, rows]) => (
                <div
                  key={item}
                  className="rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] p-5"
                >
                  <h3 className="mb-3 font-brand text-base font-semibold text-[var(--foreground)]">
                    {item}
                  </h3>
                  <div className="overflow-x-auto">
                    <table className="w-full font-body text-sm">
                      <thead>
                        <tr className="border-b border-[var(--border)] text-left text-[var(--muted-foreground)]">
                          <th className="pb-2 font-medium">Date</th>
                          <th className="pb-2 text-right font-medium">
                            {t("predicted")}
                          </th>
                          <th className="pb-2 text-right font-medium">
                            {t("lowerBound")}
                          </th>
                          <th className="pb-2 text-right font-medium">
                            {t("upperBound")}
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((row, i) => (
                          <tr
                            key={i}
                            className="border-b border-[var(--border)]/30"
                          >
                            <td className="py-1.5 text-[var(--foreground)]">
                              {String(row.date || "").slice(0, 10)}
                            </td>
                            <td className="py-1.5 text-right font-medium text-[var(--foreground)]">
                              {Number(row.predicted_quantity || 0).toFixed(1)}
                            </td>
                            <td className="py-1.5 text-right text-[var(--muted-foreground)]">
                              {Number(row.lower_bound || 0).toFixed(1)}
                            </td>
                            <td className="py-1.5 text-right text-[var(--muted-foreground)]">
                              {Number(row.upper_bound || 0).toFixed(1)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
          </div>
        )}

        {/* Empty state */}
        {!loading && forecasts.length === 0 && !error && (
          <div className="flex h-32 items-center justify-center rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)]">
            <span className="font-body text-sm text-[var(--muted-foreground)]">
              Click &quot;{t("generate")}&quot; to generate demand predictions
            </span>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
