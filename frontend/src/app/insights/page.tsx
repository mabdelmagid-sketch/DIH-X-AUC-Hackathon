"use client";

import { useState } from "react";
import { getInsights } from "@/lib/api";
import LoadingSpinner from "@/components/LoadingSpinner";

export default function InsightsPage() {
  const [briefing, setBriefing] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState("");

  async function generateBriefing(customQuery?: string) {
    setLoading(true);
    try {
      const result = await getInsights(customQuery);
      setBriefing(result.insight);
    } catch {
      setBriefing("Failed to generate insights. Make sure the API is running.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Insights</h1>
          <p className="text-sm text-gray-500">
            AI-generated daily briefing and inventory analysis
          </p>
        </div>
        <button
          onClick={() => generateBriefing()}
          disabled={loading}
          className="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 disabled:opacity-50"
        >
          {loading ? "Generating..." : "Generate Daily Briefing"}
        </button>
      </div>

      {/* Custom query */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6">
        <label className="block text-xs font-medium text-gray-600 mb-2">
          Ask a Specific Question
        </label>
        <div className="flex gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. What are the biggest risks in our inventory right now?"
            className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
          <button
            onClick={() => generateBriefing(query)}
            disabled={loading || !query.trim()}
            className="px-4 py-2 bg-gray-800 text-white text-sm rounded-lg hover:bg-gray-900 disabled:opacity-50"
          >
            Ask
          </button>
        </div>
      </div>

      {loading && <LoadingSpinner text="Analyzing inventory and generating insights..." />}

      {briefing && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="prose text-sm text-gray-700 whitespace-pre-wrap">
            {briefing}
          </div>
        </div>
      )}

      {!loading && !briefing && (
        <div className="text-center text-gray-400 py-12">
          <p>Click "Generate Daily Briefing" to get your morning inventory report</p>
        </div>
      )}
    </div>
  );
}
