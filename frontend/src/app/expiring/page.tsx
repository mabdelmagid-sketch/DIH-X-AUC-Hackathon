"use client";

import { useState } from "react";
import { sendChat, suggestPromotion } from "@/lib/api";
import LoadingSpinner from "@/components/LoadingSpinner";

interface ExpiringItem {
  title: string;
  stock: number;
  unit: string;
  category: string;
  avg_daily_sales: number;
  days_of_stock: number;
}

export default function ExpiringPage() {
  const [items, setItems] = useState<ExpiringItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [promoLoading, setPromoLoading] = useState<string | null>(null);
  const [promos, setPromos] = useState<Record<string, string>>({});

  async function loadExpiring() {
    setLoading(true);
    try {
      // Use chat with function calling to get expiring items
      const result = await sendChat(
        "List items that are expiring soon or have very low days of stock remaining. Return as a structured list with item name, stock quantity, unit, category, average daily sales, and days of stock remaining."
      );
      // Also set a sample - the chat response contains the analysis
      setItems([]);
      // Store the chat analysis as a promo for display
      setPromos({ _analysis: result.response });
    } catch {
      setPromos({ _analysis: "Failed to load expiring items. Make sure the API is running." });
    } finally {
      setLoading(false);
    }
  }

  async function generatePromo(item: ExpiringItem) {
    setPromoLoading(item.title);
    try {
      const result = await suggestPromotion({
        item: item.title,
        current_stock: item.stock,
        days_to_expiry: Math.ceil(item.days_of_stock),
        avg_daily_sales: item.avg_daily_sales,
        cost: 10, // placeholder
        price: 25, // placeholder
      });
      setPromos((prev) => ({ ...prev, [item.title]: result.suggestion }));
    } catch {
      setPromos((prev) => ({
        ...prev,
        [item.title]: "Failed to generate promotion suggestion.",
      }));
    } finally {
      setPromoLoading(null);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Expiring Items</h1>
          <p className="text-sm text-gray-500">
            Items approaching expiry or with low days of stock
          </p>
        </div>
        <button
          onClick={loadExpiring}
          disabled={loading}
          className="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 disabled:opacity-50"
        >
          {loading ? "Analyzing..." : "Analyze Expiring Items"}
        </button>
      </div>

      {loading && <LoadingSpinner text="Analyzing inventory for expiring items..." />}

      {/* Analysis from LLM */}
      {promos._analysis && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
          <h2 className="font-semibold text-gray-900 mb-3">Expiry Analysis</h2>
          <div className="prose text-sm text-gray-700 whitespace-pre-wrap">
            {promos._analysis}
          </div>
        </div>
      )}

      {/* Individual item cards */}
      {items.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {items.map((item) => (
            <div
              key={item.title}
              className="bg-white rounded-xl border border-gray-200 p-5"
            >
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-semibold text-gray-900">{item.title}</h3>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {item.category} | {item.stock} {item.unit}
                  </p>
                </div>
                <span
                  className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                    item.days_of_stock <= 2
                      ? "bg-red-100 text-red-700"
                      : item.days_of_stock <= 5
                        ? "bg-yellow-100 text-yellow-700"
                        : "bg-green-100 text-green-700"
                  }`}
                >
                  {item.days_of_stock.toFixed(1)}d remaining
                </span>
              </div>

              <div className="mt-3 text-sm text-gray-600">
                <p>Avg daily sales: {item.avg_daily_sales.toFixed(1)}</p>
              </div>

              {promos[item.title] ? (
                <div className="mt-3 p-3 bg-blue-50 rounded-lg text-sm text-gray-700 whitespace-pre-wrap">
                  {promos[item.title]}
                </div>
              ) : (
                <button
                  onClick={() => generatePromo(item)}
                  disabled={promoLoading === item.title}
                  className="mt-3 px-3 py-1.5 text-xs bg-brand-600 text-white rounded-lg hover:bg-brand-700 disabled:opacity-50"
                >
                  {promoLoading === item.title
                    ? "Generating..."
                    : "Generate Promotion"}
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {!loading && !promos._analysis && items.length === 0 && (
        <div className="text-center text-gray-400 py-12">
          <p>Click "Analyze Expiring Items" to scan your inventory</p>
        </div>
      )}
    </div>
  );
}
