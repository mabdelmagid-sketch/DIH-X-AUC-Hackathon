"use client";

import { useEffect, useState } from "react";
import { getInventory } from "@/lib/api";
import { formatNumber } from "@/lib/utils";
import LoadingSpinner from "@/components/LoadingSpinner";

export default function InventoryPage() {
  const [data, setData] = useState<Awaited<ReturnType<typeof getInventory>> | null>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getInventory(500)
      .then(setData)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingSpinner text="Loading inventory..." />;

  const items = data?.items || [];
  const filtered = search
    ? items.filter((item) =>
        String(item.title || "")
          .toLowerCase()
          .includes(search.toLowerCase())
      )
    : items;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Inventory</h1>
          <p className="text-sm text-gray-500">
            {formatNumber(data?.total_items || 0)} items total |{" "}
            <span className="text-red-600">
              {formatNumber(data?.low_stock_count || 0)} low stock
            </span>
          </p>
        </div>
      </div>

      {/* Search */}
      <div className="mb-4">
        <input
          type="text"
          placeholder="Search items..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full max-w-md px-4 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-left text-gray-600">
                <th className="px-4 py-3 font-medium">Item</th>
                <th className="px-4 py-3 font-medium">Category</th>
                <th className="px-4 py-3 font-medium text-right">Quantity</th>
                <th className="px-4 py-3 font-medium">Unit</th>
                <th className="px-4 py-3 font-medium text-right">Threshold</th>
                <th className="px-4 py-3 font-medium text-center">Status</th>
              </tr>
            </thead>
            <tbody>
              {filtered.slice(0, 100).map((item, i) => {
                const qty = Number(item.quantity) || 0;
                const threshold = Number(item.threshold) || 0;
                const ratio = threshold > 0 ? qty / threshold : 999;
                let statusColor = "bg-green-100 text-green-700";
                let statusLabel = "OK";
                if (ratio < 0.5) {
                  statusColor = "bg-red-100 text-red-700";
                  statusLabel = "Critical";
                } else if (ratio < 1) {
                  statusColor = "bg-yellow-100 text-yellow-700";
                  statusLabel = "Low";
                }

                return (
                  <tr key={i} className="border-t border-gray-100 hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-900">
                      {String(item.title || "Unknown")}
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      {String(item.category_name || "--")}
                    </td>
                    <td className="px-4 py-3 text-right">{formatNumber(qty)}</td>
                    <td className="px-4 py-3 text-gray-500">{String(item.unit || "")}</td>
                    <td className="px-4 py-3 text-right text-gray-500">
                      {threshold > 0 ? formatNumber(threshold) : "--"}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {threshold > 0 && (
                        <span
                          className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${statusColor}`}
                        >
                          {statusLabel}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {filtered.length > 100 && (
          <div className="px-4 py-3 bg-gray-50 text-xs text-gray-500 text-center">
            Showing 100 of {formatNumber(filtered.length)} items
          </div>
        )}
      </div>
    </div>
  );
}
