"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { DashboardLayout, PageHeader } from "@/components/layout";
import { simulate } from "@/lib/forecasting-api";

const EXAMPLE_SCENARIOS = [
  "What if we run 20% off on all pasta dishes this weekend?",
  "What if we stop ordering dairy products for 2 weeks?",
  "What if we add a new lunch combo deal at 79 DKK?",
  "What if weekend demand increases by 30% next month?",
  "What if our main supplier delays delivery by 3 days?",
];

export default function SimulatorPage() {
  const t = useTranslations("simulator");

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
    <DashboardLayout>
      <div className="flex flex-col gap-6">
        <PageHeader title={t("title")} description={t("description")} />

        {/* Error */}
        {error && (
          <div className="rounded-[var(--radius-m)] border border-[var(--destructive)] bg-[var(--destructive)]/10 px-4 py-3 font-body text-sm text-[var(--destructive)]">
            {error}
          </div>
        )}

        {/* Scenario input */}
        <div className="rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] p-6">
          <label className="mb-2 block font-body text-sm font-medium text-[var(--foreground)]">
            {t("describeScenario")}
          </label>
          <div className="flex gap-2">
            <input
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && runSimulation()}
              placeholder="What if we..."
              className="flex-1 rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--background)] px-4 py-2.5 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
            />
            <button
              onClick={() => runSimulation()}
              disabled={loading || !scenario.trim()}
              className="rounded-[var(--radius-pill)] bg-[var(--primary)] px-6 py-2.5 font-body text-sm font-medium text-white transition-colors hover:opacity-90 disabled:opacity-50"
            >
              {loading ? t("simulating") : t("simulate")}
            </button>
          </div>

          {/* Example scenarios */}
          <div className="mt-4">
            <p className="mb-2 font-body text-xs text-[var(--muted-foreground)]">
              {t("tryExample")}
            </p>
            <div className="flex flex-wrap gap-2">
              {EXAMPLE_SCENARIOS.map((ex) => (
                <button
                  key={ex}
                  onClick={() => {
                    setScenario(ex);
                    runSimulation(ex);
                  }}
                  disabled={loading}
                  className="rounded-[var(--radius-pill)] border border-[var(--border)] bg-[var(--background)] px-3 py-1.5 font-body text-xs text-[var(--muted-foreground)] transition-colors hover:bg-[var(--accent)] disabled:opacity-50"
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-12">
            <span className="animate-pulse font-body text-sm text-[var(--muted-foreground)]">
              Running simulation (this may take a moment)...
            </span>
          </div>
        )}

        {/* Results */}
        {result && !loading && (
          <div className="rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] p-6">
            <h2 className="mb-4 font-brand text-base font-semibold text-[var(--foreground)]">
              {t("results")}
            </h2>
            <div className="prose max-w-none whitespace-pre-wrap font-body text-sm text-[var(--foreground)]">
              {result}
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
