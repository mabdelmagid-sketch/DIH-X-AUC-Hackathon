"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { DashboardLayout, PageHeader } from "@/components/layout";
import { getInsights } from "@/lib/forecasting-api";

export default function InsightsPage() {
  const t = useTranslations("insights");

  const [briefing, setBriefing] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState("");

  async function generateBriefing(customQuery?: string) {
    setLoading(true);
    try {
      const result = await getInsights(customQuery);
      setBriefing(result.insight);
    } catch {
      setBriefing(
        "Failed to generate insights. Make sure the forecasting API is running.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <DashboardLayout>
      <div className="flex flex-col gap-6">
        <PageHeader
          title={t("title")}
          description={t("description")}
          actions={
            <button
              onClick={() => generateBriefing()}
              disabled={loading}
              className="rounded-[var(--radius-pill)] bg-[var(--primary)] px-5 py-2 font-body text-sm font-medium text-white transition-colors hover:opacity-90 disabled:opacity-50"
            >
              {loading ? "Generating..." : t("generateBriefing")}
            </button>
          }
        />

        {/* Custom query */}
        <div className="rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] p-4">
          <label className="mb-2 block font-body text-xs font-medium text-[var(--muted-foreground)]">
            {t("askQuestion")}
          </label>
          <div className="flex gap-2">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) =>
                e.key === "Enter" && query.trim() && generateBriefing(query)
              }
              placeholder={t("placeholder")}
              className="flex-1 rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--background)] px-3 py-2 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
            />
            <button
              onClick={() => generateBriefing(query)}
              disabled={loading || !query.trim()}
              className="rounded-[var(--radius-m)] bg-[var(--foreground)] px-4 py-2 font-body text-sm font-medium text-[var(--background)] transition-colors hover:opacity-90 disabled:opacity-50"
            >
              {t("ask")}
            </button>
          </div>
        </div>

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-12">
            <span className="animate-pulse font-body text-sm text-[var(--muted-foreground)]">
              Analyzing inventory and generating insights...
            </span>
          </div>
        )}

        {/* Results */}
        {briefing && !loading && (
          <div className="rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] p-6">
            <div className="prose max-w-none whitespace-pre-wrap font-body text-sm text-[var(--foreground)]">
              {briefing}
            </div>
          </div>
        )}

        {/* Empty state */}
        {!loading && !briefing && (
          <div className="flex items-center justify-center py-12 text-center">
            <span className="font-body text-sm text-[var(--muted-foreground)]">
              {t("emptyState")}
            </span>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
