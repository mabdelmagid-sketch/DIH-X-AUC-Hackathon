"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import { useTranslations } from "next-intl";
import { DashboardLayout, PageHeader } from "@/components/layout";
import { getForecast } from "@/lib/forecasting-api";

type Forecast = {
  item_title: string;
  date: string;
  predicted_quantity: number;
  lower_bound: number;
  upper_bound: number;
  demand_risk: "low" | "medium" | "high";
  is_perishable: boolean;
  safety_stock: number | null;
  model_source: string;
};

function riskColor(risk: string) {
  if (risk === "high") return { bg: "bg-red-500/15", text: "text-red-500", border: "border-red-500/30", dot: "bg-red-500" };
  if (risk === "medium") return { bg: "bg-amber-500/15", text: "text-amber-500", border: "border-amber-500/30", dot: "bg-amber-500" };
  return { bg: "bg-emerald-500/15", text: "text-emerald-500", border: "border-emerald-500/30", dot: "bg-emerald-500" };
}

function DayBar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative h-16 w-5 overflow-hidden rounded-sm bg-[var(--muted)]/30">
        <div
          className="absolute bottom-0 w-full rounded-sm bg-[var(--primary)] transition-all"
          style={{ height: `${pct}%` }}
        />
      </div>
      <span className="font-body text-[10px] tabular-nums text-[var(--muted-foreground)]">
        {value > 0 ? Math.round(value) : "-"}
      </span>
    </div>
  );
}

export default function ForecastPage() {
  const t = useTranslations("forecast");

  const [forecasts, setForecasts] = useState<Forecast[]>([]);
  const [loading, setLoading] = useState(false);
  const [daysAhead, setDaysAhead] = useState(7);
  const [itemFilter, setItemFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const autoLoaded = useRef(false);

  useEffect(() => {
    if (!autoLoaded.current) {
      autoLoaded.current = true;
      handleForecast();
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleForecast() {
    setLoading(true);
    setError(null);
    try {
      const result = await getForecast(daysAhead, itemFilter || undefined, 15);
      setForecasts(result.forecasts as Forecast[]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Forecast failed");
    } finally {
      setLoading(false);
    }
  }

  // Group forecasts by item
  const byItem = useMemo(() => {
    const map: Record<string, Forecast[]> = {};
    for (const f of forecasts) {
      const item = f.item_title || "Unknown";
      if (!map[item]) map[item] = [];
      map[item].push(f);
    }
    return map;
  }, [forecasts]);

  // Summary stats
  const stats = useMemo(() => {
    const items = Object.keys(byItem);
    const highRisk = items.filter((item) =>
      byItem[item].some((f) => f.demand_risk === "high"),
    ).length;
    const medRisk = items.filter((item) =>
      byItem[item].some((f) => f.demand_risk === "medium") &&
      !byItem[item].some((f) => f.demand_risk === "high"),
    ).length;
    const totalDemand = forecasts.reduce(
      (sum, f) => sum + (f.predicted_quantity || 0),
      0,
    );
    const perishable = items.filter((item) =>
      byItem[item].some((f) => f.is_perishable),
    ).length;
    return { total: items.length, highRisk, medRisk, totalDemand, perishable };
  }, [byItem, forecasts]);

  // Global max for bar scaling
  const globalMax = useMemo(() => {
    let max = 0;
    for (const f of forecasts) {
      if (f.predicted_quantity > max) max = f.predicted_quantity;
    }
    return max || 1;
  }, [forecasts]);

  function toggleExpand(item: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(item)) next.delete(item);
      else next.add(item);
      return next;
    });
  }

  // Derive overall risk per item
  function itemRisk(rows: Forecast[]): string {
    if (rows.some((f) => f.demand_risk === "high")) return "high";
    if (rows.some((f) => f.demand_risk === "medium")) return "medium";
    return "low";
  }

  // Sort: high risk first, then by avg demand descending
  const sortedItems = useMemo(() => {
    const riskOrder: Record<string, number> = { high: 0, medium: 1, low: 2 };
    return Object.entries(byItem).sort(([, a], [, b]) => {
      const ra = riskOrder[itemRisk(a)] ?? 2;
      const rb = riskOrder[itemRisk(b)] ?? 2;
      if (ra !== rb) return ra - rb;
      const avgA = a.reduce((s, f) => s + f.predicted_quantity, 0) / a.length;
      const avgB = b.reduce((s, f) => s + f.predicted_quantity, 0) / b.length;
      return avgB - avgA;
    });
  }, [byItem]);

  return (
    <DashboardLayout>
      <div className="flex flex-col gap-6">
        <PageHeader title={t("title")} description={t("description")} />

        {/* Error */}
        {error && (
          <div className="rounded-[var(--radius-m)] border border-[var(--destructive)] bg-[var(--destructive)]/10 px-4 py-3 font-body text-sm text-[var(--destructive)]">
            {error}
          </div>
        )}

        {/* Controls */}
        <div className="flex flex-wrap items-end gap-4 rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] p-5">
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
              onKeyDown={(e) => e.key === "Enter" && handleForecast()}
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
          <div className="flex flex-col items-center justify-center gap-3 py-16">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--muted)] border-t-[var(--primary)]" />
            <span className="font-body text-sm text-[var(--muted-foreground)]">
              Running ML models...
            </span>
          </div>
        )}

        {/* Summary Stats */}
        {!loading && stats.total > 0 && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] p-4">
              <p className="font-body text-xs text-[var(--muted-foreground)]">Products Tracked</p>
              <p className="mt-1 font-brand text-2xl font-bold text-[var(--foreground)]">{stats.total}</p>
            </div>
            <div className="rounded-[var(--radius-m)] border border-red-500/20 bg-red-500/5 p-4">
              <p className="font-body text-xs text-red-500">High Risk</p>
              <p className="mt-1 font-brand text-2xl font-bold text-red-500">{stats.highRisk}</p>
            </div>
            <div className="rounded-[var(--radius-m)] border border-amber-500/20 bg-amber-500/5 p-4">
              <p className="font-body text-xs text-amber-500">Medium Risk</p>
              <p className="mt-1 font-brand text-2xl font-bold text-amber-500">{stats.medRisk}</p>
            </div>
            <div className="rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] p-4">
              <p className="font-body text-xs text-[var(--muted-foreground)]">Total Predicted</p>
              <p className="mt-1 font-brand text-2xl font-bold text-[var(--foreground)]">
                {Math.round(stats.totalDemand).toLocaleString()}
              </p>
            </div>
          </div>
        )}

        {/* Forecast Cards */}
        {!loading && sortedItems.length > 0 && (
          <div className="flex flex-col gap-3">
            {sortedItems.map(([item, rows]) => {
              const risk = itemRisk(rows);
              const rc = riskColor(risk);
              const avgQty = rows.reduce((s, f) => s + f.predicted_quantity, 0) / rows.length;
              const maxQty = Math.max(...rows.map((f) => f.upper_bound || f.predicted_quantity));
              const safetyStock = rows.find((f) => f.safety_stock != null)?.safety_stock;
              const isExpanded = expanded.has(item);
              const perishable = rows.some((f) => f.is_perishable);

              // Get unique dates sorted
              const dateMap = new Map<string, Forecast>();
              for (const r of rows) {
                const d = String(r.date).slice(0, 10);
                if (!dateMap.has(d)) dateMap.set(d, r);
              }
              const dailyForecasts = Array.from(dateMap.values());

              return (
                <div
                  key={item}
                  className="overflow-hidden rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] transition-shadow hover:shadow-sm"
                >
                  {/* Card Header */}
                  <button
                    onClick={() => toggleExpand(item)}
                    className="flex w-full items-center gap-4 p-4 text-left transition-colors hover:bg-[var(--muted)]/30"
                  >
                    {/* Risk dot */}
                    <div className={`h-2.5 w-2.5 shrink-0 rounded-full ${rc.dot}`} />

                    {/* Item name + badges */}
                    <div className="flex min-w-0 flex-1 items-center gap-2">
                      <h3 className="truncate font-brand text-sm font-semibold text-[var(--foreground)]">
                        {item}
                      </h3>
                      <span className={`shrink-0 rounded-full px-2 py-0.5 font-body text-[10px] font-medium uppercase tracking-wide ${rc.bg} ${rc.text}`}>
                        {risk}
                      </span>
                      {perishable && (
                        <span className="shrink-0 rounded-full bg-blue-500/10 px-2 py-0.5 font-body text-[10px] font-medium uppercase tracking-wide text-blue-500">
                          Perishable
                        </span>
                      )}
                    </div>

                    {/* Mini daily bars */}
                    <div className="hidden items-end gap-1 sm:flex">
                      {dailyForecasts.slice(0, 7).map((f, i) => (
                        <DayBar key={i} value={f.predicted_quantity} max={globalMax} />
                      ))}
                    </div>

                    {/* Key numbers */}
                    <div className="flex shrink-0 items-center gap-6">
                      <div className="text-right">
                        <p className="font-body text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">
                          Avg/Day
                        </p>
                        <p className="font-brand text-lg font-bold tabular-nums text-[var(--foreground)]">
                          {avgQty.toFixed(1)}
                        </p>
                      </div>
                      {safetyStock != null && safetyStock > 0 && (
                        <div className="text-right">
                          <p className="font-body text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">
                            Safety
                          </p>
                          <p className="font-brand text-lg font-bold tabular-nums text-[var(--primary)]">
                            {safetyStock.toFixed(1)}
                          </p>
                        </div>
                      )}
                      <div className="text-right">
                        <p className="font-body text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">
                          Range
                        </p>
                        <p className="font-body text-xs tabular-nums text-[var(--muted-foreground)]">
                          {rows[0] ? Number(rows[0].lower_bound).toFixed(0) : 0}
                          {" - "}
                          {maxQty.toFixed(0)}
                        </p>
                      </div>
                    </div>

                    {/* Expand chevron */}
                    <svg
                      className={`h-4 w-4 shrink-0 text-[var(--muted-foreground)] transition-transform ${isExpanded ? "rotate-180" : ""}`}
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={2}
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>

                  {/* Expanded Detail */}
                  {isExpanded && (
                    <div className="border-t border-[var(--border)] px-4 pb-4 pt-3">
                      {/* Visual bar chart */}
                      <div className="mb-4 flex items-end gap-2">
                        {dailyForecasts.map((f, i) => {
                          const dayMax = Math.max(...dailyForecasts.map((d) => d.upper_bound || d.predicted_quantity));
                          const pct = dayMax > 0 ? (f.predicted_quantity / dayMax) * 100 : 0;
                          const lPct = dayMax > 0 ? (f.lower_bound / dayMax) * 100 : 0;
                          const uPct = dayMax > 0 ? (f.upper_bound / dayMax) * 100 : 0;
                          const dayName = new Date(f.date).toLocaleDateString("en", { weekday: "short" });
                          const dayNum = new Date(f.date).getDate();
                          return (
                            <div key={i} className="flex flex-1 flex-col items-center gap-1">
                              <div className="relative h-24 w-full max-w-[40px] overflow-hidden rounded-t-sm bg-[var(--muted)]/20">
                                {/* Confidence range */}
                                <div
                                  className="absolute w-full bg-[var(--primary)]/10"
                                  style={{
                                    bottom: `${lPct}%`,
                                    height: `${uPct - lPct}%`,
                                  }}
                                />
                                {/* Predicted bar */}
                                <div
                                  className="absolute bottom-0 w-full rounded-t-sm bg-[var(--primary)] transition-all"
                                  style={{ height: `${pct}%` }}
                                />
                              </div>
                              <span className="font-body text-[10px] font-medium text-[var(--muted-foreground)]">
                                {dayName}
                              </span>
                              <span className="font-body text-[10px] tabular-nums text-[var(--muted-foreground)]">
                                {dayNum}
                              </span>
                            </div>
                          );
                        })}
                      </div>

                      {/* Compact table */}
                      <table className="w-full font-body text-xs">
                        <thead>
                          <tr className="border-b border-[var(--border)] text-[var(--muted-foreground)]">
                            <th className="pb-1.5 text-left font-medium">Date</th>
                            <th className="pb-1.5 text-right font-medium">{t("predicted")}</th>
                            <th className="pb-1.5 text-right font-medium">{t("lowerBound")}</th>
                            <th className="pb-1.5 text-right font-medium">{t("upperBound")}</th>
                            <th className="pb-1.5 text-right font-medium">Risk</th>
                          </tr>
                        </thead>
                        <tbody>
                          {dailyForecasts.map((row, i) => {
                            const drc = riskColor(row.demand_risk);
                            return (
                              <tr key={i} className="border-b border-[var(--border)]/20">
                                <td className="py-1.5 text-[var(--foreground)]">
                                  {new Date(row.date).toLocaleDateString("en", {
                                    weekday: "short",
                                    month: "short",
                                    day: "numeric",
                                  })}
                                </td>
                                <td className="py-1.5 text-right font-medium tabular-nums text-[var(--foreground)]">
                                  {row.predicted_quantity.toFixed(1)}
                                </td>
                                <td className="py-1.5 text-right tabular-nums text-[var(--muted-foreground)]">
                                  {row.lower_bound.toFixed(1)}
                                </td>
                                <td className="py-1.5 text-right tabular-nums text-[var(--muted-foreground)]">
                                  {row.upper_bound.toFixed(1)}
                                </td>
                                <td className="py-1.5 text-right">
                                  <span className={`inline-block h-1.5 w-1.5 rounded-full ${drc.dot}`} />
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              );
            })}
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
