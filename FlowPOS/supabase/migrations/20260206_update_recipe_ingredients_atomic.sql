-- Atomic recipe ingredient replacement.
-- Deletes all existing recipe ingredients and inserts the new set in a single transaction.

CREATE OR REPLACE FUNCTION update_recipe_ingredients_atomic(
  p_recipe_id UUID,
  p_ingredients JSONB,
  p_organization_id UUID
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_recipe RECORD;
  v_item JSONB;
  v_count INTEGER := 0;
BEGIN
  -- Verify recipe exists and belongs to the organization
  SELECT id
  INTO v_recipe
  FROM recipes
  WHERE id = p_recipe_id
    AND organization_id = p_organization_id
    AND deleted_at IS NULL;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Recipe not found or does not belong to organization'
      USING ERRCODE = 'P0002';
  END IF;

  -- Delete all existing recipe ingredients
  DELETE FROM recipe_ingredients
  WHERE recipe_id = p_recipe_id;

  -- Validate p_ingredients is a non-empty array
  IF p_ingredients IS NULL OR jsonb_array_length(p_ingredients) = 0 THEN
    -- Allow clearing all ingredients; return 0
    RETURN 0;
  END IF;

  -- Insert new recipe ingredients
  FOR v_item IN SELECT * FROM jsonb_array_elements(p_ingredients)
  LOOP
    INSERT INTO recipe_ingredients (
      recipe_id,
      ingredient_id,
      quantity,
      unit,
      notes,
      is_optional,
      sort_order,
      created_at,
      updated_at
    ) VALUES (
      p_recipe_id,
      (v_item->>'ingredientId')::UUID,
      (v_item->>'quantity')::NUMERIC,
      (v_item->>'unit')::unit_of_measure,
      v_item->>'notes',
      COALESCE((v_item->>'isOptional')::BOOLEAN, false),
      COALESCE((v_item->>'sortOrder')::INTEGER, v_count),
      NOW(),
      NOW()
    );

    v_count := v_count + 1;
  END LOOP;

  RETURN v_count;
END;
$$;

COMMENT ON FUNCTION update_recipe_ingredients_atomic IS 'Atomically replaces all recipe ingredients by deleting existing ones and inserting the new set. Verifies recipe belongs to the organization.';
