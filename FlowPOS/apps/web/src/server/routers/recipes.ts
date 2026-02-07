import { z } from "zod";
import { router, protectedProcedure, adminProcedure } from "../trpc";
import { TRPCError } from "@trpc/server";

// Enum values from database
const unitOfMeasureEnum = z.enum([
  "g", "kg", "mg", "ml", "l", "cl", "oz", "lb", "fl_oz",
  "cup", "tbsp", "tsp", "piece", "each", "slice", "portion", "serving"
]);

const difficultyLevelEnum = z.enum(["EASY", "MEDIUM", "HARD"]);

// Schema validators
const recipeIdSchema = z.object({
  id: z.string().uuid(),
});

const recipeIngredientSchema = z.object({
  ingredientId: z.string().uuid(),
  quantity: z.number().positive(),
  unit: unitOfMeasureEnum,
  notes: z.string().max(255).optional(),
  isOptional: z.boolean().default(false),
  sortOrder: z.number().int().default(0),
});

const prepStepSchema = z.object({
  id: z.string().uuid(),
  order: z.number().int().min(1),
  instruction: z.string().min(1).max(500),
  duration: z.number().int().min(0).optional(),
  notes: z.string().max(255).optional(),
});

const createRecipeSchema = z.object({
  name: z.string().min(1).max(255),
  description: z.string().max(1000).optional(),
  productId: z.string().uuid().optional(), // Link to sellable product
  yieldQuantity: z.number().positive().default(1),
  yieldUnit: z.string().max(50).default("serving"),
  prepTimeMinutes: z.number().int().min(0).default(0),
  cookTimeMinutes: z.number().int().min(0).default(0),
  difficultyLevel: difficultyLevelEnum.default("MEDIUM"),
  instructions: z.string().max(5000).optional(),
  notes: z.string().max(1000).optional(),
  imageUrl: z.string().url().optional().or(z.literal("")),
  isActive: z.boolean().default(true),
  category: z.string().max(100).optional(),
  tags: z.array(z.string().max(50)).default([]),
  prepSteps: z.array(prepStepSchema).default([]),
  allergens: z.array(z.string().max(50)).default([]),
  ingredients: z.array(recipeIngredientSchema).default([]),
});

const updateRecipeSchema = createRecipeSchema.partial().extend({
  id: z.string().uuid(),
});

const listQuerySchema = z.object({
  search: z.string().optional(),
  productId: z.string().uuid().optional(),
  isActive: z.boolean().optional(),
  difficultyLevel: difficultyLevelEnum.optional(),
  limit: z.number().int().min(1).max(100).default(50),
  offset: z.number().int().min(0).default(0),
});

export const recipesRouter = router({
  // List all recipes for the organization
  list: protectedProcedure
    .input(listQuerySchema.optional())
    .query(async ({ ctx, input }) => {
      let query = ctx.db
        .from("recipes")
        .select("*, product:products(id, name, price)", { count: "exact" })
        .eq("organization_id", ctx.organizationId)
        .is("deleted_at", null)
        .order("name", { ascending: true });

      if (input?.productId) {
        query = query.eq("product_id", input.productId);
      }

      if (input?.isActive !== undefined) {
        query = query.eq("is_active", input.isActive);
      }

      if (input?.difficultyLevel) {
        query = query.eq("difficulty_level", input.difficultyLevel);
      }

      if (input?.search) {
        query = query.or(`name.ilike.%${input.search}%,description.ilike.%${input.search}%`);
      }

      const { data, error, count } = await query
        .range(input?.offset ?? 0, (input?.offset ?? 0) + (input?.limit ?? 50) - 1);

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return {
        recipes: data ?? [],
        total: count ?? 0,
      };
    }),

  // Get a single recipe with all details
  get: protectedProcedure
    .input(recipeIdSchema)
    .query(async ({ ctx, input }) => {
      const { data: recipe, error } = await ctx.db
        .from("recipes")
        .select("*, product:products(id, name, price)")
        .eq("id", input.id)
        .eq("organization_id", ctx.organizationId)
        .is("deleted_at", null)
        .single();

      if (error || !recipe) {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "Recipe not found",
        });
      }

      // Get ingredients
      const { data: ingredients, error: ingredientsError } = await ctx.db
        .from("recipe_ingredients")
        .select("*, ingredient:ingredients(id, name, unit, cost_per_unit, category, allergens)")
        .eq("recipe_id", input.id)
        .order("sort_order", { ascending: true });

      if (ingredientsError) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: ingredientsError.message,
        });
      }

      return {
        ...recipe,
        ingredients: ingredients ?? [],
      };
    }),

  // Create a new recipe
  create: adminProcedure
    .input(createRecipeSchema)
    .mutation(async ({ ctx, input }) => {
      const { ingredients, ...recipeData } = input;

      // Create recipe
      const { data: recipe, error } = await ctx.db
        .from("recipes")
        .insert({
          organization_id: ctx.organizationId,
          name: recipeData.name,
          description: recipeData.description || null,
          product_id: recipeData.productId || null,
          yield_quantity: recipeData.yieldQuantity,
          yield_unit: recipeData.yieldUnit,
          prep_time_minutes: recipeData.prepTimeMinutes,
          cook_time_minutes: recipeData.cookTimeMinutes,
          // total_time_minutes is auto-generated by database (prep + cook)
          difficulty_level: recipeData.difficultyLevel,
          instructions: recipeData.instructions || null,
          notes: recipeData.notes || null,
          image_url: recipeData.imageUrl || null,
          is_active: recipeData.isActive,
          category: recipeData.category || null,
          tags: recipeData.tags || null,
          prep_steps: recipeData.prepSteps || null,
          allergens: recipeData.allergens || null,
        })
        .select()
        .single();

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      // Add ingredients
      if (ingredients.length > 0) {
        const { error: ingredientsError } = await ctx.db
          .from("recipe_ingredients")
          .insert(
            ingredients.map((ing, index) => ({
              recipe_id: recipe.id,
              ingredient_id: ing.ingredientId,
              quantity: ing.quantity,
              unit: ing.unit,
              notes: ing.notes || null,
              is_optional: ing.isOptional,
              sort_order: ing.sortOrder ?? index,
            }))
          );

        if (ingredientsError) {
          // Rollback - delete the recipe
          await ctx.db.from("recipes").delete().eq("id", recipe.id);
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: ingredientsError.message,
          });
        }
      }

      return recipe;
    }),

  // Update an existing recipe
  update: adminProcedure
    .input(updateRecipeSchema)
    .mutation(async ({ ctx, input }) => {
      const { id, ingredients, ...updateData } = input;

      // Build update payload
      const updatePayload: Record<string, unknown> = {};
      if (updateData.name !== undefined) updatePayload.name = updateData.name;
      if (updateData.description !== undefined) updatePayload.description = updateData.description || null;
      if (updateData.productId !== undefined) updatePayload.product_id = updateData.productId || null;
      if (updateData.yieldQuantity !== undefined) updatePayload.yield_quantity = updateData.yieldQuantity;
      if (updateData.yieldUnit !== undefined) updatePayload.yield_unit = updateData.yieldUnit;
      if (updateData.prepTimeMinutes !== undefined) updatePayload.prep_time_minutes = updateData.prepTimeMinutes;
      if (updateData.cookTimeMinutes !== undefined) updatePayload.cook_time_minutes = updateData.cookTimeMinutes;
      if (updateData.difficultyLevel !== undefined) updatePayload.difficulty_level = updateData.difficultyLevel;
      if (updateData.instructions !== undefined) updatePayload.instructions = updateData.instructions || null;
      if (updateData.notes !== undefined) updatePayload.notes = updateData.notes || null;
      if (updateData.imageUrl !== undefined) updatePayload.image_url = updateData.imageUrl || null;
      if (updateData.isActive !== undefined) updatePayload.is_active = updateData.isActive;
      if (updateData.category !== undefined) updatePayload.category = updateData.category || null;
      if (updateData.tags !== undefined) updatePayload.tags = updateData.tags || null;
      if (updateData.prepSteps !== undefined) updatePayload.prep_steps = updateData.prepSteps || null;
      if (updateData.allergens !== undefined) updatePayload.allergens = updateData.allergens || null;
      
      // Note: total_time_minutes is auto-generated by database (prep + cook)

      // Update recipe if there are changes
      if (Object.keys(updatePayload).length > 0) {
        const { error } = await ctx.db
          .from("recipes")
          .update(updatePayload)
          .eq("id", id)
          .eq("organization_id", ctx.organizationId)
          .is("deleted_at", null);

        if (error) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: error.message,
          });
        }
      }

      // Update ingredients if provided (atomic - delete + insert in single transaction)
      if (ingredients !== undefined) {
        const { error: ingredientsError } = await (ctx.db.rpc as CallableFunction)(
          "update_recipe_ingredients_atomic",
          {
            p_recipe_id: id,
            p_ingredients: JSON.stringify(
              ingredients.map((ing, index) => ({
                ingredientId: ing.ingredientId,
                quantity: ing.quantity,
                unit: ing.unit,
                notes: ing.notes || null,
                isOptional: ing.isOptional ?? false,
                sortOrder: ing.sortOrder ?? index,
              }))
            ),
            p_organization_id: ctx.organizationId,
          }
        );

        if (ingredientsError) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: ingredientsError.message,
          });
        }
      }

      // Return updated recipe
      const { data: updatedRecipe, error: fetchError } = await ctx.db
        .from("recipes")
        .select("*, product:products(id, name, price)")
        .eq("id", id)
        .single();

      if (fetchError || !updatedRecipe) {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "Recipe not found",
        });
      }

      return updatedRecipe;
    }),

  // Soft delete a recipe
  delete: adminProcedure
    .input(recipeIdSchema)
    .mutation(async ({ ctx, input }) => {
      const { error } = await ctx.db
        .from("recipes")
        .update({ deleted_at: new Date().toISOString() })
        .eq("id", input.id)
        .eq("organization_id", ctx.organizationId);

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return { success: true };
    }),

  // Calculate recipe cost (using database function)
  calculateCost: protectedProcedure
    .input(recipeIdSchema)
    .query(async ({ ctx, input }) => {
      const { data, error } = await ctx.db.rpc("calculate_recipe_cost", {
        p_recipe_id: input.id,
      });

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      const result = (data as unknown[])?.[0] as {
        recipe_id: string;
        recipe_name: string;
        yield_quantity: number;
        total_ingredient_cost: number;
        cost_per_serving: number;
        ingredient_count: number;
      } | undefined;

      if (!result) {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "Recipe not found or has no ingredients",
        });
      }

      return {
        recipeId: result.recipe_id,
        recipeName: result.recipe_name,
        yieldQuantity: result.yield_quantity,
        totalIngredientCost: result.total_ingredient_cost,
        costPerServing: result.cost_per_serving,
        ingredientCount: result.ingredient_count,
      };
    }),

  // Add/update a single ingredient
  addIngredient: adminProcedure
    .input(
      z.object({
        recipeId: z.string().uuid(),
        ...recipeIngredientSchema.shape,
      })
    )
    .mutation(async ({ ctx, input }) => {
      // Verify recipe belongs to org
      const { data: recipe } = await ctx.db
        .from("recipes")
        .select("id")
        .eq("id", input.recipeId)
        .eq("organization_id", ctx.organizationId)
        .is("deleted_at", null)
        .single();

      if (!recipe) {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "Recipe not found",
        });
      }

      // Check if ingredient already exists in recipe
      const { data: existing } = await ctx.db
        .from("recipe_ingredients")
        .select("id")
        .eq("recipe_id", input.recipeId)
        .eq("ingredient_id", input.ingredientId)
        .single();

      if (existing) {
        // Update existing
        const { data, error } = await ctx.db
          .from("recipe_ingredients")
          .update({
            quantity: input.quantity,
            unit: input.unit,
            notes: input.notes || null,
            is_optional: input.isOptional,
            sort_order: input.sortOrder,
          })
          .eq("id", existing.id)
          .select("*, ingredient:ingredients(id, name, unit, cost_per_unit)")
          .single();

        if (error) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: error.message,
          });
        }

        return data;
      } else {
        // Create new
        const { data, error } = await ctx.db
          .from("recipe_ingredients")
          .insert({
            recipe_id: input.recipeId,
            ingredient_id: input.ingredientId,
            quantity: input.quantity,
            unit: input.unit,
            notes: input.notes || null,
            is_optional: input.isOptional,
            sort_order: input.sortOrder,
          })
          .select("*, ingredient:ingredients(id, name, unit, cost_per_unit)")
          .single();

        if (error) {
          throw new TRPCError({
            code: "INTERNAL_SERVER_ERROR",
            message: error.message,
          });
        }

        return data;
      }
    }),

  // Remove an ingredient from a recipe
  removeIngredient: adminProcedure
    .input(
      z.object({
        recipeId: z.string().uuid(),
        ingredientId: z.string().uuid(),
      })
    )
    .mutation(async ({ ctx, input }) => {
      // Verify recipe belongs to org
      const { data: recipe } = await ctx.db
        .from("recipes")
        .select("id")
        .eq("id", input.recipeId)
        .eq("organization_id", ctx.organizationId)
        .is("deleted_at", null)
        .single();

      if (!recipe) {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "Recipe not found",
        });
      }

      const { error } = await ctx.db
        .from("recipe_ingredients")
        .delete()
        .eq("recipe_id", input.recipeId)
        .eq("ingredient_id", input.ingredientId);

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return { success: true };
    }),

  // Duplicate a recipe
  duplicate: adminProcedure
    .input(
      z.object({
        id: z.string().uuid(),
        newName: z.string().min(1).max(255).optional(),
      })
    )
    .mutation(async ({ ctx, input }) => {
      // Get original recipe with ingredients
      const { data: original, error: fetchError } = await ctx.db
        .from("recipes")
        .select("*")
        .eq("id", input.id)
        .eq("organization_id", ctx.organizationId)
        .is("deleted_at", null)
        .single();

      if (fetchError || !original) {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "Recipe not found",
        });
      }

      // Get ingredients
      const { data: ingredients } = await ctx.db
        .from("recipe_ingredients")
        .select("*")
        .eq("recipe_id", input.id);

      // Create new recipe
      const { data: newRecipe, error: createError } = await ctx.db
        .from("recipes")
        .insert({
          organization_id: ctx.organizationId,
          name: input.newName ?? `${original.name} (Copy)`,
          description: original.description,
          product_id: null, // Don't copy product link
          yield_quantity: original.yield_quantity,
          yield_unit: original.yield_unit,
          prep_time_minutes: original.prep_time_minutes,
          cook_time_minutes: original.cook_time_minutes,
          difficulty_level: original.difficulty_level,
          instructions: original.instructions,
          notes: original.notes,
          image_url: original.image_url,
          is_active: false, // Start as inactive
        })
        .select()
        .single();

      if (createError) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: createError.message,
        });
      }

      // Copy ingredients
      if (ingredients && ingredients.length > 0) {
        await ctx.db.from("recipe_ingredients").insert(
          ingredients.map((ing) => ({
            recipe_id: newRecipe.id,
            ingredient_id: ing.ingredient_id,
            quantity: ing.quantity,
            unit: ing.unit,
            notes: ing.notes,
            is_optional: ing.is_optional,
            sort_order: ing.sort_order,
          }))
        );
      }

      return newRecipe;
    }),

  // Get recipes that use a specific ingredient
  getByIngredient: protectedProcedure
    .input(z.object({ ingredientId: z.string().uuid() }))
    .query(async ({ ctx, input }) => {
      // Get recipe IDs that use this ingredient
      const { data: recipeIngredients, error: riError } = await ctx.db
        .from("recipe_ingredients")
        .select("recipe_id")
        .eq("ingredient_id", input.ingredientId);

      if (riError) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: riError.message,
        });
      }

      const recipeIds = (recipeIngredients ?? []).map((ri) => ri.recipe_id);
      if (recipeIds.length === 0) return [];

      const { data: recipes, error } = await ctx.db
        .from("recipes")
        .select("*, product:products(id, name, price)")
        .eq("organization_id", ctx.organizationId)
        .is("deleted_at", null)
        .in("id", recipeIds);

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return recipes ?? [];
    }),

  // Get recipe suggestions for expiring ingredients
  getSuggestionsForExpiring: protectedProcedure
    .input(
      z.object({
        locationId: z.string().uuid(),
        daysThreshold: z.number().int().min(1).max(30).default(7),
      })
    )
    .query(async ({ ctx, input }) => {
      // Get expiring batches
      const { data: expiringBatches, error: batchError } = await ctx.db.rpc(
        "get_expiring_batches",
        {
          p_location_id: input.locationId,
          p_days_threshold: input.daysThreshold,
        }
      );

      if (batchError) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: batchError.message,
        });
      }

      if (!expiringBatches || expiringBatches.length === 0) {
        return [];
      }

      // Get unique ingredient IDs from expiring batches
      const expiringIngredientIds = [
        ...new Set((expiringBatches as { ingredient_id: string }[]).map((b) => b.ingredient_id)),
      ];

      // Find recipes that use these ingredients
      const { data: recipeIngredients, error: riError } = await ctx.db
        .from("recipe_ingredients")
        .select("recipe_id, ingredient_id, quantity, unit")
        .in("ingredient_id", expiringIngredientIds);

      if (riError) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: riError.message,
        });
      }

      const recipeIds = [...new Set((recipeIngredients ?? []).map((ri) => ri.recipe_id))];
      if (recipeIds.length === 0) return [];

      // Get recipes
      const { data: recipes, error: recipesError } = await ctx.db
        .from("recipes")
        .select("*, product:products(id, name, price)")
        .eq("organization_id", ctx.organizationId)
        .is("deleted_at", null)
        .eq("is_active", true)
        .in("id", recipeIds);

      if (recipesError) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: recipesError.message,
        });
      }

      // Build expiring ingredient map
      const expiringMap = new Map<string, { quantity: number; daysUntilExpiry: number; name: string }>();
      for (const batch of expiringBatches as { ingredient_id: string; ingredient_name: string; quantity: number; days_until_expiry: number }[]) {
        const existing = expiringMap.get(batch.ingredient_id);
        if (existing) {
          existing.quantity += batch.quantity;
          if (batch.days_until_expiry < existing.daysUntilExpiry) {
            existing.daysUntilExpiry = batch.days_until_expiry;
          }
        } else {
          expiringMap.set(batch.ingredient_id, {
            quantity: batch.quantity,
            daysUntilExpiry: batch.days_until_expiry,
            name: batch.ingredient_name,
          });
        }
      }

      // Build recipe suggestions with expiring ingredients info
      const suggestions = (recipes ?? []).map((recipe) => {
        const ingredientsInRecipe = (recipeIngredients ?? []).filter(
          (ri) => ri.recipe_id === recipe.id
        );
        const expiringIngredientsUsed = ingredientsInRecipe
          .filter((ri) => expiringMap.has(ri.ingredient_id))
          .map((ri) => {
            const expiring = expiringMap.get(ri.ingredient_id)!;
            return {
              ingredientId: ri.ingredient_id,
              ingredientName: expiring.name,
              quantityNeeded: ri.quantity,
              unit: ri.unit,
              quantityExpiring: expiring.quantity,
              daysUntilExpiry: expiring.daysUntilExpiry,
            };
          });

        // Calculate how many servings we can make with expiring ingredients
        const maxServings = Math.min(
          ...expiringIngredientsUsed.map((ing) =>
            Math.floor(ing.quantityExpiring / ing.quantityNeeded)
          )
        );

        return {
          recipe,
          expiringIngredientsUsed,
          maxServingsFromExpiring: maxServings,
          urgency: Math.min(...expiringIngredientsUsed.map((i) => i.daysUntilExpiry)),
        };
      });

      // Sort by urgency (lowest days until expiry first) and max servings
      return suggestions.sort((a, b) => {
        if (a.urgency !== b.urgency) return a.urgency - b.urgency;
        return b.maxServingsFromExpiring - a.maxServingsFromExpiring;
      });
    }),

  // Produce recipe (deduct ingredients from stock)
  produce: protectedProcedure
    .input(
      z.object({
        recipeId: z.string().uuid(),
        locationId: z.string().uuid(),
        quantity: z.number().int().positive().default(1),
        orderId: z.string().uuid().optional(),
      })
    )
    .mutation(async ({ ctx, input }) => {
      // Use database function to deduct ingredients
      const { data, error } = await ctx.db.rpc("deduct_recipe_ingredients", {
        p_recipe_id: input.recipeId,
        p_location_id: input.locationId,
        p_quantity: input.quantity,
        p_order_id: input.orderId,
        p_user_id: ctx.user.id,
      });

      if (error) {
        throw new TRPCError({
          code: "INTERNAL_SERVER_ERROR",
          message: error.message,
        });
      }

      return { success: data as boolean };
    }),

  // Get recipe cost breakdown
  getCostBreakdown: protectedProcedure
    .input(recipeIdSchema)
    .query(async ({ ctx, input }) => {
      // Get recipe with ingredients
      const { data: recipe } = await ctx.db
        .from("recipes")
        .select("*, product:products(id, name, price)")
        .eq("id", input.id)
        .eq("organization_id", ctx.organizationId)
        .is("deleted_at", null)
        .single();

      if (!recipe) {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "Recipe not found",
        });
      }

      const { data: ingredients } = await ctx.db
        .from("recipe_ingredients")
        .select("*, ingredient:ingredients(id, name, unit, cost_per_unit, category)")
        .eq("recipe_id", input.id)
        .order("sort_order", { ascending: true });

      // Calculate costs
      let totalCost = 0;
      const ingredientCosts = (ingredients ?? []).map((ri) => {
        const ing = ri.ingredient as { cost_per_unit: number; name: string; unit: string } | null;
        const costPerUnit = ing?.cost_per_unit ?? 0;
        const cost = ri.quantity * costPerUnit;
        totalCost += cost;

        return {
          ingredientId: ri.ingredient_id,
          ingredientName: ing?.name ?? "Unknown",
          quantity: ri.quantity,
          unit: ri.unit,
          costPerUnit,
          totalCost: cost,
          percentageOfTotal: 0, // Will calculate after we know total
        };
      });

      // Calculate percentages
      for (const ic of ingredientCosts) {
        ic.percentageOfTotal = totalCost > 0 ? (ic.totalCost / totalCost) * 100 : 0;
      }

      const costPerServing = recipe.yield_quantity > 0 ? totalCost / recipe.yield_quantity : 0;
      const productData = recipe.product as { price: number } | null;
      const sellingPrice = productData?.price ?? 0;
      const profitMargin = sellingPrice > 0 ? ((sellingPrice - costPerServing) / sellingPrice) * 100 : 0;

      return {
        recipeId: recipe.id,
        recipeName: recipe.name,
        yieldQuantity: recipe.yield_quantity,
        yieldUnit: recipe.yield_unit,
        totalIngredientCost: totalCost,
        costPerServing,
        sellingPrice,
        profitPerServing: sellingPrice - costPerServing,
        profitMargin,
        ingredients: ingredientCosts,
      };
    }),
});
