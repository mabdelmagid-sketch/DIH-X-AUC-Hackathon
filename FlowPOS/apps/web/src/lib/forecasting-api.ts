/**
 * Typed API client for the FlowPOS Forecasting microservice.
 *
 * In production, calls the forecasting API directly (bypasses Next.js rewrite
 * which has a 30s proxy timeout too short for ML model inference).
 * In development, uses the Next.js rewrite proxy.
 */

function getApiBase(): string {
  if (typeof window !== "undefined" && window.location.hostname !== "localhost") {
    return "https://forecasting-api-production-2809.up.railway.app/api";
  }
  return "/api/forecast";
}

const API_BASE = getApiBase();

async function fetcher<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status}: ${body}`);
  }
  return res.json();
}

// --- Health ---

export async function getHealth() {
  return fetcher<{
    status: string;
    timestamp: string;
    model_loaded: boolean;
    llm_available: boolean;
    tools_available: boolean;
  }>("/health");
}

// --- Data ---

export async function getTables() {
  return fetcher<{
    tables: { name: string; rows: number }[];
    count: number;
  }>("/data/tables");
}

export async function getInventory(limit = 200) {
  return fetcher<{
    items: Record<string, unknown>[];
    total_items: number;
    low_stock_count: number;
    expiring_soon_count: number;
  }>(`/data/inventory?limit=${limit}`);
}

export async function getSales(limit = 1000) {
  return fetcher<{
    sales: Record<string, unknown>[];
    total_records: number;
    date_range: { min: string | null; max: string | null };
  }>(`/data/sales?limit=${limit}`);
}

export async function getMenu(limit = 100) {
  return fetcher<{
    items: Record<string, unknown>[];
    total: number;
  }>(`/data/menu?limit=${limit}`);
}

// --- Places ---

export async function getPlaces() {
  return fetcher<{
    places: { id: number; title: string; order_count: number }[];
  }>("/data/places");
}

// --- Model ---

export async function getForecast(
  daysAhead = 7,
  itemFilter?: string,
  topN?: number,
  placeId?: number,
) {
  return fetcher<{
    forecasts: Record<string, unknown>[];
    generated_at: string;
  }>("/forecast", {
    method: "POST",
    body: JSON.stringify({
      days_ahead: daysAhead,
      item_filter: itemFilter || null,
      top_n: topN || null,
      place_id: placeId || null,
    }),
  });
}

export async function getFeatureImportance(topN = 20) {
  return fetcher<{
    features: { feature: string; importance: number }[];
    model_metrics: Record<string, number>;
  }>(`/model/features?top_n=${topN}`);
}

// --- Chat ---

export async function sendChat(message: string) {
  return fetcher<{
    response: string;
    context_used: boolean;
  }>("/chat", {
    method: "POST",
    body: JSON.stringify({ message, include_context: true }),
  });
}

export type SSEEvent =
  | { type: "tool_call"; tool: string; args: Record<string, unknown> }
  | { type: "token"; content: string }
  | { type: "done" }
  | { type: "error"; message: string };

export async function* streamChat(
  message: string,
): AsyncGenerator<SSEEvent> {
  const res = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, include_context: true }),
  });

  if (!res.ok) throw new Error(`Stream error ${res.status}`);
  if (!res.body) throw new Error("No response body");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          const event = JSON.parse(line.slice(6)) as SSEEvent;
          yield event;
        } catch {
          // skip malformed SSE
        }
      }
    }
  }
}

// --- Insights ---

export async function getInsights(query?: string, storeContext?: string) {
  return fetcher<{
    insight: string;
    generated_at: string;
  }>("/insights", {
    method: "POST",
    body: JSON.stringify({
      query: query || null,
      store_context: storeContext || null,
    }),
  });
}

// --- Simulator ---

export async function simulate(scenario: string) {
  return fetcher<{
    scenario: string;
    analysis: string;
    generated_at: string;
  }>("/simulate", {
    method: "POST",
    body: JSON.stringify({ scenario }),
  });
}

// --- Promotions ---

export async function suggestPromotion(params: {
  item: string;
  current_stock: number;
  days_to_expiry: number;
  avg_daily_sales: number;
  cost: number;
  price: number;
}) {
  const qs = new URLSearchParams(
    Object.entries(params).map(([k, v]) => [k, String(v)]),
  ).toString();
  return fetcher<{
    item: string;
    suggestion: string;
  }>(`/suggest-promotion?${qs}`, { method: "POST" });
}
