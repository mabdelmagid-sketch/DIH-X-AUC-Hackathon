import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { generateEmbedding } from "@/lib/embeddings";

const DEEPSEEK_API_KEY = process.env.DEEPSEEK_API_KEY;
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY!;

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { productName, existingIngredients, organizationId } = body as {
      productName: string;
      existingIngredients: Array<{ id: string; name: string; unit: string }>;
      organizationId?: string;
    };

    if (!productName?.trim()) {
      return NextResponse.json(
        { error: "Product name is required" },
        { status: 400 }
      );
    }

    // ---- Step 1: Try embedding similarity search ----
    try {
      const embedding = await generateEmbedding(productName.trim());

      if (embedding.length === 768) {
        const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);

        // Find similar recipes GLOBALLY (cross-org learning)
        const { data: matches } = await supabase.rpc("match_recipes", {
          query_embedding: JSON.stringify(embedding),
          match_threshold: 0.4,
          match_count: 3,
          p_organization_id: null, // Search all orgs for best match
        });

        if (matches && matches.length > 0) {
          // Get the best match's ingredients
          const bestMatch = matches[0];
          const { data: recipeIngredients } = await supabase
            .from("recipe_ingredients")
            .select("quantity, unit, ingredient:ingredients(id, name, unit)")
            .eq("recipe_id", bestMatch.id)
            .order("sort_order", { ascending: true });

          if (recipeIngredients && recipeIngredients.length > 0) {
            const suggestions = recipeIngredients.map((ri: {
              quantity: number;
              unit: string;
              ingredient: { id: string; name: string; unit: string } | null;
            }) => ({
              name: ri.ingredient?.name ?? "Unknown",
              quantity: ri.quantity,
              unit: ri.unit,
              source: "embedding",
              matchedRecipe: bestMatch.name,
              similarity: bestMatch.similarity,
            }));

            return NextResponse.json({
              suggestions,
              source: "embedding",
              matchedRecipe: bestMatch.name,
              similarity: Math.round(bestMatch.similarity * 100),
            });
          }
        }
      }
    } catch (embErr) {
      console.error("Embedding search failed, falling back to LLM:", embErr);
    }

    // ---- Step 2: Fallback to DeepSeek LLM ----
    if (!DEEPSEEK_API_KEY) {
      return NextResponse.json(
        { suggestions: [], source: "none", error: "No matching recipes found and AI service not configured" },
        { status: 200 }
      );
    }

    const ingredientList = existingIngredients
      .map((i) => `- ${i.name} (unit: ${i.unit})`)
      .join("\n");

    const prompt = `You are a restaurant recipe assistant. Given a menu product name, suggest the ingredients and approximate quantities needed to make one serving.

Product name: "${productName}"

${ingredientList ? `Available ingredients in the system:\n${ingredientList}\n\nIMPORTANT: You MUST use ingredient names EXACTLY as they appear in the available list above. Only suggest ingredients that exist in the list. If none match, return an empty array.` : "No ingredients exist in the system yet. Suggest common ingredient names with quantities."}

Respond ONLY with a valid JSON array. Each element should have:
- "name": exact ingredient name (must match available list if provided)
- "quantity": number (amount needed for one serving)
- "unit": one of: g, kg, mg, ml, l, cl, oz, lb, fl_oz, cup, tbsp, tsp, piece, each, slice, portion, serving

JSON array only, no other text:`;

    const response = await fetch("https://api.deepseek.com/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${DEEPSEEK_API_KEY}`,
      },
      body: JSON.stringify({
        model: "deepseek-chat",
        messages: [{ role: "user", content: prompt }],
        temperature: 0.3,
        max_tokens: 1000,
      }),
    });

    if (!response.ok) {
      const errText = await response.text();
      console.error("DeepSeek API error:", errText);
      return NextResponse.json(
        { suggestions: [], source: "error", error: "AI service error" },
        { status: 200 }
      );
    }

    const data = await response.json();
    const content = data.choices?.[0]?.message?.content?.trim() ?? "[]";

    let suggestions: Array<{ name: string; quantity: number; unit: string }>;
    try {
      const cleaned = content.replace(/```json?\n?/g, "").replace(/```/g, "").trim();
      suggestions = JSON.parse(cleaned);
      if (!Array.isArray(suggestions)) suggestions = [];
    } catch {
      console.error("Failed to parse AI response:", content);
      suggestions = [];
    }

    return NextResponse.json({
      suggestions: suggestions.map((s) => ({ ...s, source: "llm" })),
      source: "llm",
    });
  } catch (error) {
    console.error("AI suggestion error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
