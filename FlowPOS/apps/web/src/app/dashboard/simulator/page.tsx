"use client";

import { useState, useMemo } from "react";
import { useTranslations } from "next-intl";
import { DashboardLayout, PageHeader } from "@/components/layout";
import { Icon } from "@/components/ui";
import { simulate } from "@/lib/forecasting-api";

const EXAMPLE_SCENARIOS = [
  "What if we run 20% off on all pasta dishes this weekend?",
  "What if we stop ordering dairy products for 2 weeks?",
  "What if we add a new lunch combo deal at 79 DKK?",
  "What if weekend demand increases by 30% next month?",
  "What if our main supplier delays delivery by 3 days?",
];

/** Lightweight markdown-ish renderer for simulation results. */
function SimulationResult({ text }: { text: string }) {
  const blocks = useMemo(() => {
    const lines = text.split("\n");
    const result: { type: string; content: string; rows?: string[][] }[] = [];
    let tableRows: string[][] = [];
    let inTable = false;

    const flushTable = () => {
      if (tableRows.length > 0) {
        result.push({ type: "table", content: "", rows: [...tableRows] });
        tableRows = [];
      }
      inTable = false;
    };

    for (const line of lines) {
      const trimmed = line.trim();

      // Table row
      if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
        // Skip separator rows (|---|---|)
        if (/^\|[\s\-|]+\|$/.test(trimmed)) {
          inTable = true;
          continue;
        }
        inTable = true;
        const cells = trimmed.split("|").slice(1, -1).map((c) => c.trim());
        tableRows.push(cells);
        continue;
      }

      if (inTable) flushTable();

      if (trimmed.startsWith("### ")) {
        result.push({ type: "h3", content: trimmed.slice(4) });
      } else if (trimmed.startsWith("## ")) {
        result.push({ type: "h2", content: trimmed.slice(3) });
      } else if (trimmed.startsWith("**") && trimmed.endsWith("**")) {
        result.push({ type: "bold", content: trimmed.slice(2, -2) });
      } else if (trimmed.startsWith("- ")) {
        result.push({ type: "li", content: trimmed.slice(2) });
      } else if (trimmed === "") {
        result.push({ type: "br", content: "" });
      } else {
        result.push({ type: "p", content: trimmed });
      }
    }
    if (inTable) flushTable();

    return result;
  }, [text]);

  return (
    <div className="flex flex-col gap-1">
      {blocks.map((block, i) => {
        if (block.type === "h2")
          return (
            <h2 key={i} className="mt-2 font-brand text-base font-semibold text-[var(--foreground)]">
              {block.content}
            </h2>
          );
        if (block.type === "h3")
          return (
            <h3 key={i} className="mt-3 font-brand text-sm font-semibold text-[var(--foreground)]">
              {block.content}
            </h3>
          );
        if (block.type === "bold")
          return (
            <p key={i} className="mt-2 font-body text-sm font-semibold text-[var(--foreground)]">
              {block.content}
            </p>
          );
        if (block.type === "li")
          return (
            <div key={i} className="flex gap-2 ps-2 font-body text-sm text-[var(--foreground)]">
              <span className="text-[var(--muted-foreground)]">&bull;</span>
              <span>{renderInlineBold(block.content)}</span>
            </div>
          );
        if (block.type === "table" && block.rows) {
          const [header, ...body] = block.rows;
          return (
            <div key={i} className="my-2 overflow-x-auto rounded-[var(--radius-m)] border border-[var(--border)]">
              <table className="w-full text-sm">
                {header && (
                  <thead>
                    <tr className="border-b border-[var(--border)] bg-[var(--secondary)]">
                      {header.map((cell, j) => (
                        <th key={j} className="px-3 py-2 text-start font-brand text-xs font-medium text-[var(--foreground)]">
                          {cell}
                        </th>
                      ))}
                    </tr>
                  </thead>
                )}
                <tbody>
                  {body.map((row, ri) => (
                    <tr key={ri} className={ri < body.length - 1 ? "border-b border-[var(--border)]" : ""}>
                      {row.map((cell, j) => (
                        <td key={j} className="px-3 py-1.5 font-body text-xs text-[var(--foreground)]">
                          {cell}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        if (block.type === "br") return <div key={i} className="h-1" />;
        return (
          <p key={i} className="font-body text-sm text-[var(--foreground)]">
            {renderInlineBold(block.content)}
          </p>
        );
      })}
    </div>
  );
}

/** Render **bold** segments within a line. */
function renderInlineBold(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? (
      <strong key={i} className="font-semibold">{part.slice(2, -2)}</strong>
    ) : (
      <span key={i}>{part}</span>
    )
  );
}

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
          <div className="flex items-center gap-3 rounded-[var(--radius-m)] border border-[var(--destructive)] bg-[var(--destructive)]/10 px-4 py-3 font-body text-sm text-[var(--destructive)]">
            <Icon name="error" size={18} />
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
              className="flex items-center gap-2 rounded-[var(--radius-pill)] bg-[var(--primary)] px-6 py-2.5 font-body text-sm font-medium text-white transition-colors hover:opacity-90 disabled:opacity-50"
            >
              {loading && (
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
              )}
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
            <div className="flex flex-col items-center gap-3">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
              <span className="font-body text-sm text-[var(--muted-foreground)]">
                Analyzing scenario against sales data...
              </span>
            </div>
          </div>
        )}

        {/* Results */}
        {result && !loading && (
          <div className="rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] p-6">
            <div className="mb-4 flex items-center gap-2">
              <Icon name="analytics" size={20} className="text-[var(--primary)]" />
              <h2 className="font-brand text-base font-semibold text-[var(--foreground)]">
                {t("results")}
              </h2>
            </div>
            <SimulationResult text={result} />
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
