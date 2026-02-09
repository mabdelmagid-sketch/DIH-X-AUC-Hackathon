const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
const GEMINI_EMBED_URL = "https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent";

/**
 * Generate an embedding vector using Gemini's text-embedding-004 (free tier).
 * Returns a 768-dimensional float array.
 */
export async function generateEmbedding(text: string): Promise<number[]> {
  if (!GEMINI_API_KEY) {
    throw new Error("GEMINI_API_KEY not configured");
  }

  const response = await fetch(`${GEMINI_EMBED_URL}?key=${GEMINI_API_KEY}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "models/text-embedding-004",
      content: { parts: [{ text }] },
    }),
  });

  if (!response.ok) {
    const err = await response.text();
    console.error("Gemini embedding error:", err);
    throw new Error("Embedding generation failed");
  }

  const data = await response.json();
  return data.embedding?.values ?? [];
}

/**
 * Build a text representation of a recipe for embedding.
 * e.g. "Cappuccino: Espresso 30ml, Whole Milk 200ml, Vanilla Syrup 10ml"
 */
export function buildRecipeText(
  recipeName: string,
  ingredients: Array<{ name: string; quantity: number; unit: string }>
): string {
  const ingredientStr = ingredients
    .map((i) => `${i.name} ${i.quantity}${i.unit}`)
    .join(", ");
  return ingredientStr ? `${recipeName}: ${ingredientStr}` : recipeName;
}
