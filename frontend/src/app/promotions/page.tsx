"use client";

import { useState } from "react";
import { sendChat } from "@/lib/api";
import LoadingSpinner from "@/components/LoadingSpinner";

export default function PromotionsPage() {
  const [suggestions, setSuggestions] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [customPrompt, setCustomPrompt] = useState("");

  async function generatePromotions(prompt?: string) {
    setLoading(true);
    try {
      const result = await sendChat(
        prompt ||
          "Based on current inventory levels and sales trends, suggest 3-5 promotions I should run this week to reduce waste and boost revenue. For each promotion, include the item, discount percentage, expected impact, and messaging."
      );
      setSuggestions(result.response);
    } catch {
      setSuggestions("Failed to generate promotions. Make sure the API is running.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Promotions</h1>
          <p className="text-sm text-gray-500">
            AI-generated promotion suggestions to reduce waste and boost sales
          </p>
        </div>
        <button
          onClick={() => generatePromotions()}
          disabled={loading}
          className="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 disabled:opacity-50"
        >
          {loading ? "Generating..." : "Generate Promotions"}
        </button>
      </div>

      {/* Custom prompt */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6">
        <label className="block text-xs font-medium text-gray-600 mb-2">
          Custom Promotion Request
        </label>
        <div className="flex gap-2">
          <input
            value={customPrompt}
            onChange={(e) => setCustomPrompt(e.target.value)}
            placeholder="e.g. Suggest a bundle deal for slow-moving drinks"
            className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
          <button
            onClick={() => generatePromotions(customPrompt)}
            disabled={loading || !customPrompt.trim()}
            className="px-4 py-2 bg-gray-800 text-white text-sm rounded-lg hover:bg-gray-900 disabled:opacity-50"
          >
            Ask
          </button>
        </div>
      </div>

      {loading && <LoadingSpinner text="Analyzing data and generating promotions..." />}

      {suggestions && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="font-semibold text-gray-900 mb-4">
            Promotion Suggestions
          </h2>
          <div className="prose text-sm text-gray-700 whitespace-pre-wrap">
            {suggestions}
          </div>
        </div>
      )}

      {!loading && !suggestions && (
        <div className="text-center text-gray-400 py-12">
          <p>
            Click "Generate Promotions" to get AI-powered promotion suggestions
          </p>
        </div>
      )}
    </div>
  );
}
