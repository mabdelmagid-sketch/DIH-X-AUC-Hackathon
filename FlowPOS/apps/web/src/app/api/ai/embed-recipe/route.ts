import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { generateEmbedding, buildRecipeText } from "@/lib/embeddings";

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY!;

/**
 * POST /api/ai/embed-recipe
 * Generates and stores an embedding for a recipe.
 * Called after recipe creation to enable similarity search.
 *
 * Body: { recipeId: string }
 * OR:   { embedAll: true }  — to backfill all recipes without embeddings
 */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);

    // ---- Backfill all recipes ----
    if (body.embedAll) {
      const { data: recipes } = await supabase
        .from("recipes")
        .select("id, name")
        .is("embedding", null)
        .is("deleted_at", null)
        .limit(100);

      if (!recipes || recipes.length === 0) {
        return NextResponse.json({ embedded: 0, message: "No recipes to embed" });
      }

      let embedded = 0;
      for (const recipe of recipes) {
        try {
          // Get ingredients
          const { data: ingredients } = await supabase
            .from("recipe_ingredients")
            .select("quantity, unit, ingredient:ingredients(name)")
            .eq("recipe_id", recipe.id);

          const ingredientList = (ingredients ?? []).map((ri: {
            quantity: number;
            unit: string;
            ingredient: { name: string } | null;
          }) => ({
            name: ri.ingredient?.name ?? "",
            quantity: ri.quantity,
            unit: ri.unit,
          }));

          const text = buildRecipeText(recipe.name, ingredientList);
          const embedding = await generateEmbedding(text);

          if (embedding.length === 768) {
            await supabase
              .from("recipes")
              .update({ embedding: JSON.stringify(embedding) })
              .eq("id", recipe.id);
            embedded++;
          }
        } catch (err) {
          console.error(`Failed to embed recipe ${recipe.id}:`, err);
        }
      }

      return NextResponse.json({ embedded, total: recipes.length });
    }

    // ---- Single recipe ----
    const { recipeId } = body as { recipeId: string };
    if (!recipeId) {
      return NextResponse.json({ error: "recipeId required" }, { status: 400 });
    }

    // Get recipe with ingredients
    const { data: recipe } = await supabase
      .from("recipes")
      .select("id, name")
      .eq("id", recipeId)
      .single();

    if (!recipe) {
      return NextResponse.json({ error: "Recipe not found" }, { status: 404 });
    }

    const { data: ingredients } = await supabase
      .from("recipe_ingredients")
      .select("quantity, unit, ingredient:ingredients(name)")
      .eq("recipe_id", recipeId);

    const ingredientList = (ingredients ?? []).map((ri: {
      quantity: number;
      unit: string;
      ingredient: { name: string } | null;
    }) => ({
      name: ri.ingredient?.name ?? "",
      quantity: ri.quantity,
      unit: ri.unit,
    }));

    const text = buildRecipeText(recipe.name, ingredientList);
    const embedding = await generateEmbedding(text);

    if (embedding.length !== 768) {
      return NextResponse.json({ error: "Invalid embedding dimension" }, { status: 500 });
    }

    const { error } = await supabase
      .from("recipes")
      .update({ embedding: JSON.stringify(embedding) })
      .eq("id", recipeId);

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    return NextResponse.json({ success: true, recipeId, textEmbedded: text });
  } catch (error) {
    console.error("Embed recipe error:", error);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
