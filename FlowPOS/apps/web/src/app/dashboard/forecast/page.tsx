"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import { useTranslations } from "next-intl";
import { DashboardLayout, PageHeader } from "@/components/layout";
import { getForecast } from "@/lib/forecasting-api";
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
  const [selectedItem, setSelectedItem] = useState<string | null>(null);
  const [view, setView] = useState<ViewMode>("overview");
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
        safetyStock: Math.round(safety * 10) / 10,
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
                      name === "avgDemand" ? "Avg Demand/Day" : "Safety Stock",
                    ]}
                    labelFormatter={(label: string) => {
                      const item = overviewBarData.find((d) => d.name === label);
                      return item?.fullName ?? label;
                    }}
                  />
                  <Legend
                    formatter={(value) =>
                      value === "avgDemand" ? "Avg Demand/Day" : "Safety Stock"
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
