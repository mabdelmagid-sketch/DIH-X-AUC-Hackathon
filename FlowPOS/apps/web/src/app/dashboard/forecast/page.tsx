"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import { useTranslations } from "next-intl";
import { DashboardLayout, PageHeader } from "@/components/layout";
import { getForecast, getPlaces } from "@/lib/forecasting-api";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  Cell,
} from "recharts";

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

type ViewMode = "overview" | "detail";

const RISK_COLORS = {
  high: { fill: "#ef4444", bg: "bg-red-500/15", text: "text-red-500", dot: "bg-red-500" },
  medium: { fill: "#f59e0b", bg: "bg-amber-500/15", text: "text-amber-500", dot: "bg-amber-500" },
  low: { fill: "#10b981", bg: "bg-emerald-500/15", text: "text-emerald-500", dot: "bg-emerald-500" },
};

function riskColor(risk: string) {
  return RISK_COLORS[risk as keyof typeof RISK_COLORS] ?? RISK_COLORS.low;
}

export default function ForecastPage() {
  const t = useTranslations("forecast");

  const [forecasts, setForecasts] = useState<Forecast[]>([]);
  const [loading, setLoading] = useState(false);
  const [daysAhead, setDaysAhead] = useState(7);
  const [itemFilter, setItemFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [topN, setTopN] = useState(15);
  const [selectedItem, setSelectedItem] = useState<string | null>(null);
  const [view, setView] = useState<ViewMode>("overview");
  const [placeId, setPlaceId] = useState<number | undefined>(undefined);
  const [places, setPlaces] = useState<{ id: number; title: string; order_count: number }[]>([]);
  const [placesLoading, setPlacesLoading] = useState(true);
  const autoLoaded = useRef(false);

  useEffect(() => {
    getPlaces()
      .then((res) => setPlaces(res.places))
      .catch(() => {})
      .finally(() => setPlacesLoading(false));
  }, []);

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
      const result = await getForecast(daysAhead, itemFilter || undefined, topN || undefined, placeId);
      setForecasts(result.forecasts as Forecast[]);
      setSelectedItem(null);
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

  // Stacked bar data: avg predicted qty per item for the overview chart
  const overviewBarData = useMemo(() => {
    return sortedItems.map(([item, rows]) => {
      const avg = rows.reduce((s, f) => s + f.predicted_quantity, 0) / rows.length;
      const risk = itemRisk(rows);
      const safety = rows.find((f) => f.safety_stock != null)?.safety_stock ?? 0;
      return {
        name: item.length > 20 ? item.slice(0, 18) + "..." : item,
        fullName: item,
        avgDemand: Math.round(avg * 10) / 10,
        safetyStock: Math.round((avg + safety) * 10) / 10,
        risk,
      };
    });
  }, [sortedItems]);

  // Aggregated daily total demand across all items
  const dailyTotalData = useMemo(() => {
    const dateMap: Record<string, { predicted: number; lower: number; upper: number }> = {};
    for (const f of forecasts) {
      const d = f.date.slice(0, 10);
      if (!dateMap[d]) dateMap[d] = { predicted: 0, lower: 0, upper: 0 };
      dateMap[d].predicted += f.predicted_quantity;
      dateMap[d].lower += f.lower_bound;
      dateMap[d].upper += f.upper_bound;
    }
    return Object.entries(dateMap)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, vals]) => ({
        date: new Date(date).toLocaleDateString("en", { weekday: "short", month: "short", day: "numeric" }),
        predicted: Math.round(vals.predicted),
        lower: Math.round(vals.lower),
        upper: Math.round(vals.upper),
        range: [Math.round(vals.lower), Math.round(vals.upper)],
      }));
  }, [forecasts]);

  // Per-item area chart data
  const selectedItemData = useMemo(() => {
    if (!selectedItem || !byItem[selectedItem]) return [];
    const rows = byItem[selectedItem];
    const dateMap = new Map<string, Forecast>();
    for (const r of rows) {
      const d = r.date.slice(0, 10);
      if (!dateMap.has(d)) dateMap.set(d, r);
    }
    return Array.from(dateMap.values())
      .sort((a, b) => a.date.localeCompare(b.date))
      .map((f) => ({
        date: new Date(f.date).toLocaleDateString("en", { weekday: "short", month: "short", day: "numeric" }),
        predicted: Math.round(f.predicted_quantity * 10) / 10,
        lower: Math.round(f.lower_bound * 10) / 10,
        upper: Math.round(f.upper_bound * 10) / 10,
        range: [Math.round(f.lower_bound * 10) / 10, Math.round(f.upper_bound * 10) / 10],
      }));
  }, [selectedItem, byItem]);

  // Risk distribution for donut-style summary
  const riskDistribution = useMemo(() => {
    return [
      { name: "High Risk", value: stats.highRisk, color: "#ef4444" },
      { name: "Medium Risk", value: stats.medRisk, color: "#f59e0b" },
      { name: "Low Risk", value: stats.total - stats.highRisk - stats.medRisk, color: "#10b981" },
    ];
  }, [stats]);

  // ── Actionable insights derived from forecast data ──

  // Tomorrow's prep list: first forecast day per item
  const tomorrowPrep = useMemo(() => {
    if (forecasts.length === 0) return [];
    const allDates = [...new Set(forecasts.map((f) => f.date.slice(0, 10)))].sort();
    const tomorrow = allDates[0];
    if (!tomorrow) return [];
    return sortedItems
      .map(([item, rows]) => {
        const row = rows.find((f) => f.date.slice(0, 10) === tomorrow);
        if (!row) return null;
        const risk = itemRisk(rows);
        return {
          item,
          qty: Math.ceil(row.predicted_quantity),
          upper: Math.ceil(row.upper_bound),
          risk,
          perishable: row.is_perishable,
          safety: row.safety_stock ?? 0,
        };
      })
      .filter(Boolean) as {
        item: string; qty: number; upper: number;
        risk: string; perishable: boolean; safety: number;
      }[];
  }, [forecasts, sortedItems]);

  // Peak demand day
  const peakDay = useMemo(() => {
    if (dailyTotalData.length === 0) return null;
    let best = dailyTotalData[0];
    for (const d of dailyTotalData) {
      if (d.predicted > best.predicted) best = d;
    }
    return best;
  }, [dailyTotalData]);

  // Slowest day
  const slowestDay = useMemo(() => {
    if (dailyTotalData.length === 0) return null;
    let worst = dailyTotalData[0];
    for (const d of dailyTotalData) {
      if (d.predicted < worst.predicted) worst = d;
    }
    return worst;
  }, [dailyTotalData]);

  // Items with high volatility (wide confidence band relative to predicted)
  const volatileItems = useMemo(() => {
    return sortedItems
      .map(([item, rows]) => {
        const avgPred = rows.reduce((s, f) => s + f.predicted_quantity, 0) / rows.length;
        const avgSpread = rows.reduce((s, f) => s + (f.upper_bound - f.lower_bound), 0) / rows.length;
        const volatility = avgPred > 0 ? avgSpread / avgPred : 0;
        return { item, volatility, avgPred, avgSpread };
      })
      .filter((v) => v.volatility > 0.5)
      .sort((a, b) => b.volatility - a.volatility)
      .slice(0, 5);
  }, [sortedItems]);

  // Trending items: compare first half vs second half of forecast period
  const trendingItems = useMemo(() => {
    return sortedItems
      .map(([item, rows]) => {
        const sorted = [...rows].sort((a, b) => a.date.localeCompare(b.date));
        const mid = Math.floor(sorted.length / 2);
        if (mid === 0) return null;
        const firstHalf = sorted.slice(0, mid);
        const secondHalf = sorted.slice(mid);
        const avgFirst = firstHalf.reduce((s, f) => s + f.predicted_quantity, 0) / firstHalf.length;
        const avgSecond = secondHalf.reduce((s, f) => s + f.predicted_quantity, 0) / secondHalf.length;
        const change = avgFirst > 0 ? ((avgSecond - avgFirst) / avgFirst) * 100 : 0;
        return { item, change, avgFirst, avgSecond, risk: itemRisk(rows) };
      })
      .filter(Boolean)
      .filter((t) => t && Math.abs(t.change) > 5)
      .sort((a, b) => Math.abs(b!.change) - Math.abs(a!.change))
      .slice(0, 6) as { item: string; change: number; avgFirst: number; avgSecond: number; risk: string }[];
  }, [sortedItems]);

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

          <div>
            <label className="mb-1 block font-body text-xs font-medium text-[var(--muted-foreground)]">
              Restaurant
            </label>
            <select
              value={placeId ?? ""}
              onChange={(e) => setPlaceId(e.target.value ? Number(e.target.value) : undefined)}
              disabled={placesLoading}
              className="w-52 rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--background)] px-3 py-2 font-body text-sm text-[var(--foreground)]"
            >
              <option value="">All restaurants</option>
              {places.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title} ({p.order_count.toLocaleString()} tracked)
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block font-body text-xs font-medium text-[var(--muted-foreground)]">
              Products (by sales)
            </label>
            <select
              value={topN}
              onChange={(e) => setTopN(Number(e.target.value))}
              className="rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--background)] px-3 py-2 font-body text-sm text-[var(--foreground)]"
            >
              <option value={10}>Best 10</option>
              <option value={15}>Best 15</option>
              <option value={25}>Best 25</option>
              <option value={50}>Best 50</option>
              <option value={0}>All products</option>
            </select>
          </div>

          <button
            onClick={handleForecast}
            disabled={loading}
            className="rounded-[var(--radius-pill)] bg-[var(--primary)] px-6 py-2 font-body text-sm font-medium text-white transition-colors hover:opacity-90 disabled:opacity-50"
          >
            {loading ? t("generating") : t("generate")}
          </button>

          {/* View toggle */}
          {!loading && stats.total > 0 && (
            <div className="ml-auto flex overflow-hidden rounded-[var(--radius-m)] border border-[var(--border)]">
              <button
                onClick={() => { setView("overview"); setSelectedItem(null); }}
                className={`px-3 py-2 font-body text-xs font-medium transition-colors ${
                  view === "overview"
                    ? "bg-[var(--primary)] text-white"
                    : "bg-[var(--background)] text-[var(--muted-foreground)] hover:bg-[var(--muted)]/50"
                }`}
              >
                Overview
              </button>
              <button
                onClick={() => setView("detail")}
                className={`px-3 py-2 font-body text-xs font-medium transition-colors ${
                  view === "detail"
                    ? "bg-[var(--primary)] text-white"
                    : "bg-[var(--background)] text-[var(--muted-foreground)] hover:bg-[var(--muted)]/50"
                }`}
              >
                By Product
              </button>
            </div>
          )}
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
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
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
            <div className="rounded-[var(--radius-m)] border border-emerald-500/20 bg-emerald-500/5 p-4">
              <p className="font-body text-xs text-emerald-500">Low Risk</p>
              <p className="mt-1 font-brand text-2xl font-bold text-emerald-500">
                {stats.total - stats.highRisk - stats.medRisk}
              </p>
            </div>
            <div className="rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] p-4">
              <p className="font-body text-xs text-[var(--muted-foreground)]">Total Predicted</p>
              <p className="mt-1 font-brand text-2xl font-bold text-[var(--foreground)]">
                {Math.round(stats.totalDemand).toLocaleString()}
              </p>
            </div>
          </div>
        )}

        {/* ──────── ACTIONABLE INSIGHTS ──────── */}
        {!loading && stats.total > 0 && view === "overview" && (
          <div className="flex flex-col gap-4">
            {/* Quick Action Cards Row */}
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {/* Peak Day */}
              {peakDay && (
                <div className="flex items-start gap-3 rounded-[var(--radius-m)] border border-orange-500/20 bg-gradient-to-br from-orange-500/5 to-transparent p-4">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-orange-500/15 text-orange-500">
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/><path d="m9 16 2 2 4-4"/></svg>
                  </div>
                  <div>
                    <p className="font-body text-xs font-semibold text-orange-500">Peak Day</p>
                    <p className="font-brand text-sm font-bold text-[var(--foreground)]">{peakDay.date}</p>
                    <p className="font-body text-xs text-[var(--muted-foreground)]">
                      {peakDay.predicted} units expected &mdash; schedule extra staff
                    </p>
                  </div>
                </div>
              )}

              {/* Slowest Day */}
              {slowestDay && (
                <div className="flex items-start gap-3 rounded-[var(--radius-m)] border border-blue-500/20 bg-gradient-to-br from-blue-500/5 to-transparent p-4">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blue-500/15 text-blue-500">
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>
                  </div>
                  <div>
                    <p className="font-body text-xs font-semibold text-blue-500">Slowest Day</p>
                    <p className="font-brand text-sm font-bold text-[var(--foreground)]">{slowestDay.date}</p>
                    <p className="font-body text-xs text-[var(--muted-foreground)]">
                      {slowestDay.predicted} units &mdash; reduce prep, run promos
                    </p>
                  </div>
                </div>
              )}

              {/* Perishable Alert */}
              {stats.perishable > 0 && (
                <div className="flex items-start gap-3 rounded-[var(--radius-m)] border border-red-500/20 bg-gradient-to-br from-red-500/5 to-transparent p-4">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-red-500/15 text-red-500">
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
                  </div>
                  <div>
                    <p className="font-body text-xs font-semibold text-red-500">Waste Watch</p>
                    <p className="font-brand text-sm font-bold text-[var(--foreground)]">{stats.perishable} perishable items</p>
                    <p className="font-body text-xs text-[var(--muted-foreground)]">
                      Prep to predicted qty only &mdash; don&apos;t overbatch
                    </p>
                  </div>
                </div>
              )}
            </div>

            {/* Trending Items */}
            {trendingItems.length > 0 && (
              <div className="rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] p-5">
                <h3 className="mb-3 font-brand text-sm font-semibold text-[var(--foreground)]">
                  Demand Trends This Week
                </h3>
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {trendingItems.map((t) => (
                    <button
                      key={t.item}
                      onClick={() => { setSelectedItem(t.item); setView("detail"); }}
                      className="flex items-center gap-3 rounded-lg border border-[var(--border)] bg-[var(--background)] p-3 text-left transition-colors hover:border-[var(--primary)]/40"
                    >
                      <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                        t.change > 0
                          ? "bg-emerald-500/15 text-emerald-500"
                          : "bg-red-500/15 text-red-500"
                      }`}>
                        {t.change > 0 ? "+" : ""}{Math.round(t.change)}%
                      </div>
                      <div className="min-w-0">
                        <p className="truncate font-body text-xs font-medium text-[var(--foreground)]">{t.item}</p>
                        <p className="font-body text-[10px] text-[var(--muted-foreground)]">
                          {t.change > 0 ? "Rising demand" : "Declining demand"} &mdash; {t.avgSecond.toFixed(1)}/day
                        </p>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Tomorrow's Prep List */}
            {tomorrowPrep.length > 0 && (
              <div className="rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] p-5">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="font-brand text-sm font-semibold text-[var(--foreground)]">
                    Tomorrow&apos;s Prep Plan
                  </h3>
                  <span className="font-body text-[10px] uppercase tracking-wider text-[var(--muted-foreground)]">
                    Predicted &rarr; Safe Max
                  </span>
                </div>
                <div className="space-y-1.5">
                  {tomorrowPrep.map((p) => {
                    const rc = riskColor(p.risk);
                    return (
                      <div
                        key={p.item}
                        className="flex items-center gap-3 rounded-lg px-3 py-2 transition-colors hover:bg-[var(--muted)]/30"
                      >
                        <span className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${rc.dot}`} />
                        <span className="min-w-0 flex-1 truncate font-body text-sm text-[var(--foreground)]">
                          {p.item}
                        </span>
                        {p.perishable && (
                          <span className="shrink-0 rounded bg-blue-500/10 px-1.5 py-0.5 font-body text-[9px] font-medium uppercase text-blue-500">
                            Perish
                          </span>
                        )}
                        <div className="flex shrink-0 items-center gap-1.5 font-brand tabular-nums">
                          <span className="text-sm font-bold text-[var(--foreground)]">{p.qty}</span>
                          <span className="text-xs text-[var(--muted-foreground)]">&rarr;</span>
                          <span className="text-xs text-[var(--muted-foreground)]">{p.upper}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
                <p className="mt-3 font-body text-[10px] text-[var(--muted-foreground)]">
                  Prep to the predicted quantity. The &quot;Safe Max&quot; covers 95% demand scenarios. Perishable items: prep to predicted only.
                </p>
              </div>
            )}

            {/* Volatile Items Warning */}
            {volatileItems.length > 0 && (
              <div className="rounded-[var(--radius-m)] border border-amber-500/20 bg-amber-500/5 p-4">
                <div className="flex items-center gap-2 mb-2">
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-amber-500"><path d="M2 20h.01"/><path d="M7 20v-4"/><path d="M12 20v-8"/><path d="M17 20V8"/><path d="M22 4v16"/></svg>
                  <h4 className="font-body text-xs font-semibold text-amber-600 dark:text-amber-400">Unpredictable Demand</h4>
                </div>
                <div className="flex flex-wrap gap-2">
                  {volatileItems.map((v) => (
                    <button
                      key={v.item}
                      onClick={() => { setSelectedItem(v.item); setView("detail"); }}
                      className="rounded-full border border-amber-500/20 bg-[var(--card)] px-3 py-1 font-body text-xs text-[var(--foreground)] transition-colors hover:border-amber-500/50"
                    >
                      {v.item.length > 22 ? v.item.slice(0, 20) + "..." : v.item}
                      <span className="ml-1.5 text-amber-500">&#177;{Math.round(v.avgSpread)}</span>
                    </button>
                  ))}
                </div>
                <p className="mt-2 font-body text-[10px] text-amber-600/80 dark:text-amber-400/80">
                  These items have wide confidence bands. Keep flexible stock and check daily actuals.
                </p>
              </div>
            )}
          </div>
        )}

        {/* ──────── OVERVIEW VIEW ──────── */}
        {!loading && stats.total > 0 && view === "overview" && (
          <div className="flex flex-col gap-6">
            {/* Total Daily Demand Area Chart */}
            <div className="rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] p-5">
              <h3 className="mb-4 font-brand text-sm font-semibold text-[var(--foreground)]">
                Total Daily Demand Forecast
              </h3>
              <ResponsiveContainer width="100%" height={280}>
                <AreaChart data={dailyTotalData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                  <defs>
                    <linearGradient id="gradPredicted" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="var(--primary)" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="var(--primary)" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="gradRange" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="var(--primary)" stopOpacity={0.1} />
                      <stop offset="95%" stopColor="var(--primary)" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="date" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} />
                  <YAxis tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} />
                  <Tooltip
                    contentStyle={{
                      background: "var(--card)",
                      border: "1px solid var(--border)",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                  />
                  <Area type="monotone" dataKey="upper" stroke="none" fill="url(#gradRange)" name="Upper Bound" />
                  <Area type="monotone" dataKey="lower" stroke="none" fill="transparent" name="Lower Bound" />
                  <Area
                    type="monotone"
                    dataKey="predicted"
                    stroke="var(--primary)"
                    strokeWidth={2.5}
                    fill="url(#gradPredicted)"
                    name="Predicted"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            {/* Per-Item Horizontal Bar Chart */}
            <div className="rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] p-5">
              <h3 className="mb-4 font-brand text-sm font-semibold text-[var(--foreground)]">
                Avg Daily Demand by Product
              </h3>
              <ResponsiveContainer width="100%" height={Math.max(300, overviewBarData.length * 40)}>
                <BarChart
                  data={overviewBarData}
                  layout="vertical"
                  margin={{ top: 5, right: 20, bottom: 5, left: 10 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} />
                  <YAxis
                    type="category"
                    dataKey="name"
                    tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                    width={150}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "var(--card)",
                      border: "1px solid var(--border)",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                    formatter={(value: number, name: string) => [
                      value.toFixed(1),
                      name === "avgDemand" ? "Avg Demand/Day" : "Recommended Prep",
                    ]}
                    labelFormatter={(label: string) => {
                      const item = overviewBarData.find((d) => d.name === label);
                      return item?.fullName ?? label;
                    }}
                  />
                  <Legend
                    formatter={(value) =>
                      value === "avgDemand" ? "Avg Demand/Day" : "Recommended Prep"
                    }
                  />
                  <Bar dataKey="avgDemand" radius={[0, 4, 4, 0]} name="avgDemand">
                    {overviewBarData.map((entry, idx) => (
                      <Cell
                        key={idx}
                        fill={RISK_COLORS[entry.risk as keyof typeof RISK_COLORS]?.fill ?? "#10b981"}
                        cursor="pointer"
                        onClick={() => {
                          setSelectedItem(entry.fullName);
                          setView("detail");
                        }}
                      />
                    ))}
                  </Bar>
                  <Bar dataKey="safetyStock" fill="var(--primary)" radius={[0, 4, 4, 0]} opacity={0.3} name="safetyStock" />
                </BarChart>
              </ResponsiveContainer>
              <p className="mt-2 font-body text-[10px] text-[var(--muted-foreground)]">
                Click a bar to see daily breakdown. Colors: <span className="text-red-500">High risk</span> / <span className="text-amber-500">Medium</span> / <span className="text-emerald-500">Low</span>
              </p>
            </div>

            {/* Risk Distribution */}
            <div className="grid gap-3 sm:grid-cols-3">
              {riskDistribution.map((r) => (
                <div
                  key={r.name}
                  className="flex items-center gap-3 rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] p-4"
                >
                  <div
                    className="h-10 w-10 rounded-full"
                    style={{ background: `${r.color}20`, border: `2px solid ${r.color}` }}
                  />
                  <div>
                    <p className="font-body text-xs text-[var(--muted-foreground)]">{r.name}</p>
                    <p className="font-brand text-xl font-bold" style={{ color: r.color }}>
                      {r.value} <span className="font-body text-xs font-normal text-[var(--muted-foreground)]">products</span>
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ──────── DETAIL VIEW ──────── */}
        {!loading && stats.total > 0 && view === "detail" && (
          <div className="flex flex-col gap-4">
            {/* Item selector */}
            <div className="flex flex-wrap gap-2">
              {sortedItems.map(([item, rows]) => {
                const risk = itemRisk(rows);
                const rc = riskColor(risk);
                const isActive = selectedItem === item;
                return (
                  <button
                    key={item}
                    onClick={() => setSelectedItem(item)}
                    className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 font-body text-xs font-medium transition-all ${
                      isActive
                        ? "bg-[var(--primary)] text-white shadow-sm"
                        : `border border-[var(--border)] bg-[var(--card)] text-[var(--foreground)] hover:border-[var(--primary)]/40`
                    }`}
                  >
                    <span className={`inline-block h-2 w-2 rounded-full ${isActive ? "bg-white" : rc.dot}`} />
                    {item.length > 25 ? item.slice(0, 23) + "..." : item}
                  </button>
                );
              })}
            </div>

            {/* Selected item chart */}
            {selectedItem && byItem[selectedItem] && (
              <div className="rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] p-5">
                <div className="mb-4 flex items-center gap-3">
                  <div className={`h-3 w-3 rounded-full ${riskColor(itemRisk(byItem[selectedItem])).dot}`} />
                  <h3 className="font-brand text-base font-semibold text-[var(--foreground)]">
                    {selectedItem}
                  </h3>
                  {byItem[selectedItem].some((f) => f.is_perishable) && (
                    <span className="rounded-full bg-blue-500/10 px-2 py-0.5 font-body text-[10px] font-medium uppercase tracking-wide text-blue-500">
                      Perishable
                    </span>
                  )}
                  <span className={`rounded-full px-2 py-0.5 font-body text-[10px] font-medium uppercase tracking-wide ${riskColor(itemRisk(byItem[selectedItem])).bg} ${riskColor(itemRisk(byItem[selectedItem])).text}`}>
                    {itemRisk(byItem[selectedItem])} risk
                  </span>
                </div>

                {/* Area chart with confidence band */}
                <ResponsiveContainer width="100%" height={300}>
                  <AreaChart data={selectedItemData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                    <defs>
                      <linearGradient id="gradItemPred" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="var(--primary)" stopOpacity={0.4} />
                        <stop offset="95%" stopColor="var(--primary)" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="date" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} />
                    <YAxis tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} />
                    <Tooltip
                      contentStyle={{
                        background: "var(--card)",
                        border: "1px solid var(--border)",
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                    />
                    <Area type="monotone" dataKey="upper" stroke="#94a3b820" fill="#94a3b810" name="Upper Bound" />
                    <Area type="monotone" dataKey="lower" stroke="#94a3b820" fill="var(--card)" name="Lower Bound" />
                    <Area
                      type="monotone"
                      dataKey="predicted"
                      stroke="var(--primary)"
                      strokeWidth={2.5}
                      fill="url(#gradItemPred)"
                      name="Predicted"
                      dot={{ r: 4, fill: "var(--primary)" }}
                      activeDot={{ r: 6 }}
                    />
                  </AreaChart>
                </ResponsiveContainer>

                {/* Key stats row */}
                {(() => {
                  const rows = byItem[selectedItem];
                  const avg = rows.reduce((s, f) => s + f.predicted_quantity, 0) / rows.length;
                  const maxQ = Math.max(...rows.map((f) => f.upper_bound));
                  const minQ = Math.min(...rows.map((f) => f.lower_bound));
                  const safety = rows.find((f) => f.safety_stock != null)?.safety_stock;
                  const totalPeriod = rows.reduce((s, f) => s + f.predicted_quantity, 0);
                  return (
                    <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
                      <div className="rounded-[var(--radius-m)] bg-[var(--muted)]/30 p-3">
                        <p className="font-body text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">Avg/Day</p>
                        <p className="font-brand text-lg font-bold tabular-nums text-[var(--foreground)]">{avg.toFixed(1)}</p>
                      </div>
                      <div className="rounded-[var(--radius-m)] bg-[var(--muted)]/30 p-3">
                        <p className="font-body text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">Total ({daysAhead}d)</p>
                        <p className="font-brand text-lg font-bold tabular-nums text-[var(--foreground)]">{Math.round(totalPeriod)}</p>
                      </div>
                      <div className="rounded-[var(--radius-m)] bg-[var(--muted)]/30 p-3">
                        <p className="font-body text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">Range</p>
                        <p className="font-body text-sm tabular-nums text-[var(--muted-foreground)]">{minQ.toFixed(0)} - {maxQ.toFixed(0)}</p>
                      </div>
                      {safety != null && safety > 0 && (
                        <div className="rounded-[var(--radius-m)] bg-[var(--primary)]/10 p-3">
                          <p className="font-body text-[10px] uppercase tracking-wide text-[var(--primary)]">Safety Stock</p>
                          <p className="font-brand text-lg font-bold tabular-nums text-[var(--primary)]">{safety.toFixed(1)}</p>
                        </div>
                      )}
                      <div className="rounded-[var(--radius-m)] bg-[var(--muted)]/30 p-3">
                        <p className="font-body text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">Model</p>
                        <p className="font-body text-xs text-[var(--muted-foreground)]">{rows[0]?.model_source || "n/a"}</p>
                      </div>
                    </div>
                  );
                })()}
              </div>
            )}

            {/* Prompt to select if nothing selected */}
            {!selectedItem && (
              <div className="flex h-48 items-center justify-center rounded-[var(--radius-m)] border border-dashed border-[var(--border)] bg-[var(--card)]">
                <span className="font-body text-sm text-[var(--muted-foreground)]">
                  Select a product above to view its forecast chart
                </span>
              </div>
            )}
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
