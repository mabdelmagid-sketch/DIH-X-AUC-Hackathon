"use client";

import { useState, useMemo } from "react";
import { useTranslations } from "next-intl";
import { DashboardLayout, PageHeader } from "@/components/layout";
import { getInsights } from "@/lib/forecasting-api";

/** Simple markdown-to-HTML for LLM output (bold, italic, headers, lists, line breaks) */
function renderMarkdown(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    // Headers
    .replace(/^### (.+)$/gm, '<h4 class="font-brand text-base font-semibold mt-4 mb-1">$1</h4>')
    .replace(/^## (.+)$/gm, '<h3 class="font-brand text-lg font-semibold mt-5 mb-2">$1</h3>')
    .replace(/^# (.+)$/gm, '<h2 class="font-brand text-xl font-bold mt-6 mb-2">$1</h2>')
    // Bold + italic
    .replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>")
    // Bold
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    // Italic
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    // Unordered list items
    .replace(/^[\s]*[-•] (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
    // Numbered list items
    .replace(/^[\s]*(\d+)\. (.+)$/gm, '<li class="ml-4 list-decimal"><span>$2</span></li>')
    // Emoji alerts
    .replace(/🚨/g, '<span class="text-red-500">🚨</span>')
    // Line breaks
    .replace(/\n\n/g, '<div class="mb-3"></div>')
    .replace(/\n/g, "<br/>");
}

const STORE_CONTEXT = `This is FlowPOS, a modern coffee shop & cafe. Our actual menu products are:
- Hot Drinks: Flat White, Cappuccino, Americano, Chai Latte, Hot Chocolate, Green Tea
- Cold Drinks: Iced Latte, Fresh Orange Juice, Green Smoothie, Berry Blast Smoothie
- Breakfast: Eggs Benedict, Avocado & Egg Sandwich, Full Danish Breakfast, Acai Bowl, Granola & Yoghurt
- Bakery: Butter Croissant, Pain au Chocolat, Cinnamon Roll, Almond Croissant
- Lunch: Turkey Club Wrap, Falafel Pita, Grilled Cheese, Smoked Salmon Bagel
- Salads: Caesar Salad, Greek Salad, Quinoa Bowl, Thai Chicken Salad
- Snacks & Desserts: Hummus & Crackers, Carrot Cake Slice, Chocolate Brownie, Fruit Tart
Key ingredients: Espresso Beans, Whole Milk, Oat Milk, Croissant Dough, Fresh Berries, Avocado, Smoked Salmon, Chicken Breast, Falafel Mix.
Focus your analysis ONLY on these cafe products and their ingredients. Ignore any items not on our menu.`;

export default function InsightsPage() {
  const t = useTranslations("insights");

  const [briefing, setBriefing] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState("");

  async function generateBriefing(customQuery?: string) {
    setLoading(true);
    try {
      const result = await getInsights(customQuery, STORE_CONTEXT);
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
            <div
              className="prose prose-sm max-w-none font-body text-sm text-[var(--foreground)] [&_strong]:font-semibold [&_strong]:text-[var(--foreground)] [&_h2]:text-[var(--foreground)] [&_h3]:text-[var(--foreground)] [&_h4]:text-[var(--foreground)] [&_li]:text-[var(--muted-foreground)]"
              dangerouslySetInnerHTML={{ __html: renderMarkdown(briefing) }}
            />
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
