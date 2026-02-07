"use client";

import { useState } from "react";
import { getForecast, trainModel } from "@/lib/api";
import LoadingSpinner from "@/components/LoadingSpinner";

export default function ForecastPage() {
  const [forecasts, setForecasts] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(false);
  const [training, setTraining] = useState(false);
  const [daysAhead, setDaysAhead] = useState(7);
  const [itemFilter, setItemFilter] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleTrain() {
    setTraining(true);
    setError(null);
    setMessage(null);
    try {
      const result = await trainModel(false);
      setMessage(
        `${result.message}${result.metrics ? ` | MAE: ${result.metrics.mae}, R2: ${result.metrics.r2}` : ""}`
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Training failed");
    } finally {
      setTraining(false);
    }
  }

  async function handleForecast() {
    setLoading(true);
    setError(null);
    try {
      const result = await getForecast(daysAhead, itemFilter || undefined);
      setForecasts(result.forecasts);
      setMessage(`Generated ${result.forecasts.length} forecasts at ${result.generated_at}`);
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
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Demand Forecast</h1>
        <p className="text-sm text-gray-500">
          Train the model and generate demand predictions
        </p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">
          {error}
        </div>
      )}
      {message && (
        <div className="bg-blue-50 border border-blue-200 text-blue-700 px-4 py-3 rounded-lg mb-4 text-sm">
          {message}
        </div>
      )}

      {/* Controls */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
        <div className="flex flex-wrap gap-4 items-end">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Days Ahead
            </label>
            <select
              value={daysAhead}
              onChange={(e) => setDaysAhead(Number(e.target.value))}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
            >
              <option value={7}>7 days</option>
              <option value={14}>14 days</option>
              <option value={30}>30 days</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Item Filter (optional)
            </label>
            <input
              value={itemFilter}
              onChange={(e) => setItemFilter(e.target.value)}
              placeholder="e.g. Coffee"
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm w-48"
            />
          </div>

          <button
            onClick={handleTrain}
            disabled={training}
            className="px-4 py-2 bg-gray-800 text-white text-sm rounded-lg hover:bg-gray-900 disabled:opacity-50"
          >
            {training ? "Training..." : "Train Model"}
          </button>

          <button
            onClick={handleForecast}
            disabled={loading}
            className="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 disabled:opacity-50"
          >
            {loading ? "Forecasting..." : "Generate Forecast"}
          </button>
        </div>
      </div>

      {loading && <LoadingSpinner text="Generating forecasts..." />}

      {/* Results */}
      {Object.keys(byItem).length > 0 && (
        <div className="space-y-4">
          {Object.entries(byItem)
            .slice(0, 20)
            .map(([item, rows]) => (
              <div
                key={item}
                className="bg-white rounded-xl border border-gray-200 p-5"
              >
                <h3 className="font-semibold text-gray-900 mb-3">{item}</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-gray-500 border-b border-gray-200">
                        <th className="pb-2 font-medium">Date</th>
                        <th className="pb-2 font-medium text-right">Predicted</th>
                        <th className="pb-2 font-medium text-right">Lower</th>
                        <th className="pb-2 font-medium text-right">Upper</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row, i) => (
                        <tr key={i} className="border-b border-gray-50">
                          <td className="py-1.5">
                            {String(row.date || "").slice(0, 10)}
                          </td>
                          <td className="py-1.5 text-right font-medium">
                            {Number(row.predicted_quantity || 0).toFixed(1)}
                          </td>
                          <td className="py-1.5 text-right text-gray-500">
                            {Number(row.lower_bound || 0).toFixed(1)}
                          </td>
                          <td className="py-1.5 text-right text-gray-500">
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
    </div>
  );
}
