"use client";

import { useState } from "react";
import { simulate } from "@/lib/api";
import LoadingSpinner from "@/components/LoadingSpinner";

const EXAMPLE_SCENARIOS = [
  "What if we run 20% off on all pasta dishes this weekend?",
  "What if we stop ordering dairy products for 2 weeks?",
  "What if we add a new lunch combo deal at 79 DKK?",
  "What if weekend demand increases by 30% next month?",
  "What if our main supplier delays delivery by 3 days?",
];

export default function SimulatorPage() {
  const [scenario, setScenario] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runSimulation(s?: string) {
    const input = s || scenario;
    if (!input.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await simulate(input);
      setResult(res.analysis);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Simulation failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">What-If Simulator</h1>
        <p className="text-sm text-gray-500">
          Simulate business scenarios and see projected impact on inventory, revenue,
          and waste
        </p>
      </div>

      {/* Scenario input */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Describe your scenario
        </label>
        <div className="flex gap-2">
          <input
            value={scenario}
            onChange={(e) => setScenario(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && runSimulation()}
            placeholder="What if we..."
            className="flex-1 px-4 py-2.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
          <button
            onClick={() => runSimulation()}
            disabled={loading || !scenario.trim()}
            className="px-6 py-2.5 bg-brand-600 text-white text-sm font-medium rounded-lg hover:bg-brand-700 disabled:opacity-50"
          >
            {loading ? "Simulating..." : "Simulate"}
          </button>
        </div>

        {/* Example scenarios */}
        <div className="mt-4">
          <p className="text-xs text-gray-500 mb-2">Try an example:</p>
          <div className="flex flex-wrap gap-2">
            {EXAMPLE_SCENARIOS.map((ex) => (
              <button
                key={ex}
                onClick={() => {
                  setScenario(ex);
                  runSimulation(ex);
                }}
                disabled={loading}
                className="text-xs px-3 py-1.5 rounded-full bg-gray-100 text-gray-600 hover:bg-gray-200 transition-colors disabled:opacity-50"
              >
                {ex}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">
          {error}
        </div>
      )}

      {loading && <LoadingSpinner text="Running simulation (this may take a moment)..." />}

      {result && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="font-semibold text-gray-900 mb-4">Simulation Results</h2>
          <div className="prose text-sm text-gray-700 whitespace-pre-wrap">
            {result}
          </div>
        </div>
      )}
    </div>
  );
}
