"use client";

import { useEffect, useState } from "react";
import { getHealth, getInventory, getSales } from "@/lib/api";
import { formatNumber } from "@/lib/utils";
import KPICard from "@/components/KPICard";
import LoadingSpinner from "@/components/LoadingSpinner";

export default function DashboardPage() {
  const [health, setHealth] = useState<Awaited<ReturnType<typeof getHealth>> | null>(null);
  const [inventory, setInventory] = useState<Awaited<ReturnType<typeof getInventory>> | null>(null);
  const [salesData, setSalesData] = useState<Awaited<ReturnType<typeof getSales>> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [h, inv, s] = await Promise.all([
          getHealth().catch(() => null),
          getInventory().catch(() => null),
          getSales(500).catch(() => null),
        ]);
        setHealth(h);
        setInventory(inv);
        setSalesData(s);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load data");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) return <LoadingSpinner text="Loading dashboard..." />;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-sm text-gray-500">FlowCast Inventory Intelligence Overview</p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span
            className={`w-2 h-2 rounded-full ${health ? "bg-green-400" : "bg-red-400"}`}
          />
          {health ? "API Connected" : "API Offline"}
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-6 text-sm">
          {error}
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <KPICard
          title="Total Items"
          value={inventory ? formatNumber(inventory.total_items) : "--"}
          subtitle="In inventory catalog"
          color="blue"
        />
        <KPICard
          title="Low Stock"
          value={inventory ? formatNumber(inventory.low_stock_count) : "--"}
          subtitle="Below reorder threshold"
          color={inventory && inventory.low_stock_count > 0 ? "red" : "green"}
        />
        <KPICard
          title="Sales Records"
          value={salesData ? formatNumber(salesData.total_records) : "--"}
          subtitle="Daily aggregated"
          color="green"
        />
        <KPICard
          title="Model Status"
          value={health?.model_loaded ? "Trained" : "Not Trained"}
          subtitle={health?.llm_available ? "LLM available" : "LLM unavailable"}
          color={health?.model_loaded ? "green" : "yellow"}
        />
      </div>

      {/* System Status */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 mb-8">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">System Status</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatusBadge label="API" active={!!health} />
          <StatusBadge label="Forecast Model" active={!!health?.model_loaded} />
          <StatusBadge label="LLM (Claude)" active={!!health?.llm_available} />
          <StatusBadge label="Function Calling" active={!!health?.tools_available} />
        </div>
      </div>

      {/* Sales date range */}
      {salesData && salesData.date_range.min && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 mb-8">
          <h2 className="text-lg font-semibold text-gray-900 mb-2">Data Coverage</h2>
          <p className="text-sm text-gray-600">
            Sales data from <span className="font-medium">{salesData.date_range.min}</span> to{" "}
            <span className="font-medium">{salesData.date_range.max}</span>
          </p>
          <p className="text-sm text-gray-500 mt-1">
            {formatNumber(salesData.total_records)} daily item-level sales records
          </p>
        </div>
      )}

      {/* Quick sample of inventory */}
      {inventory && inventory.items.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            Recent Inventory ({inventory.items.length} of {formatNumber(inventory.total_items)})
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-200">
                  <th className="pb-2 font-medium">Item</th>
                  <th className="pb-2 font-medium">Quantity</th>
                  <th className="pb-2 font-medium">Unit</th>
                  <th className="pb-2 font-medium">Threshold</th>
                  <th className="pb-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {inventory.items.slice(0, 15).map((item, i) => {
                  const qty = Number(item.quantity) || 0;
                  const threshold = Number(item.threshold) || 0;
                  const isLow = threshold > 0 && qty < threshold;
                  return (
                    <tr key={i} className="border-b border-gray-100">
                      <td className="py-2 font-medium text-gray-900">
                        {String(item.title || "Unknown")}
                      </td>
                      <td className="py-2">{qty}</td>
                      <td className="py-2 text-gray-500">{String(item.unit || "")}</td>
                      <td className="py-2 text-gray-500">{threshold || "--"}</td>
                      <td className="py-2">
                        <span
                          className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                            isLow
                              ? "bg-red-100 text-red-700"
                              : "bg-green-100 text-green-700"
                          }`}
                        >
                          {isLow ? "Low" : "OK"}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function StatusBadge({ label, active }: { label: string; active: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <span
        className={`w-3 h-3 rounded-full ${active ? "bg-green-400" : "bg-gray-300"}`}
      />
      <span className="text-sm text-gray-700">{label}</span>
    </div>
  );
}
