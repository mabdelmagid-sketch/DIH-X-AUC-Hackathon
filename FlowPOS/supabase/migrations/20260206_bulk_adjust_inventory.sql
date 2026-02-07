-- Bulk adjust inventory for multiple products atomically.
-- Locks all affected inventory_items rows FOR UPDATE to prevent concurrent modifications.
-- Floors quantity at 0 using GREATEST.

CREATE OR REPLACE FUNCTION bulk_adjust_inventory(
  p_location_id UUID,
  p_items JSONB,
  p_organization_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_item JSONB;
  v_inv RECORD;
  v_new_quantity INTEGER;
  v_results JSONB := '[]'::JSONB;
  v_product_id UUID;
  v_adjustment INTEGER;
BEGIN
  -- Validate p_items is a non-empty array
  IF p_items IS NULL OR jsonb_array_length(p_items) = 0 THEN
    RAISE EXCEPTION 'p_items must be a non-empty JSON array'
      USING ERRCODE = 'P0001';
  END IF;

  -- Verify location belongs to the organization
  IF NOT EXISTS (
    SELECT 1 FROM locations
    WHERE id = p_location_id AND organization_id = p_organization_id
  ) THEN
    RAISE EXCEPTION 'Location not found or does not belong to organization'
      USING ERRCODE = 'P0002';
  END IF;

  -- Lock all affected inventory_items rows FOR UPDATE
  -- This prevents concurrent modifications during the transaction
  PERFORM ii.id
  FROM inventory_items ii
  WHERE ii.location_id = p_location_id
    AND ii.product_id IN (
      SELECT (elem->>'productId')::UUID
      FROM jsonb_array_elements(p_items) AS elem
    )
  FOR UPDATE OF ii;

  -- Process each item
  FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
  LOOP
    v_product_id := (v_item->>'productId')::UUID;
    v_adjustment := (v_item->>'adjustment')::INTEGER;

    -- Fetch the inventory item
    SELECT *
    INTO v_inv
    FROM inventory_items
    WHERE product_id = v_product_id
      AND location_id = p_location_id;

    IF NOT FOUND THEN
      RAISE EXCEPTION 'Inventory item not found for product % at location %',
        v_product_id, p_location_id
        USING ERRCODE = 'P0002';
    END IF;

    -- Calculate new quantity, floor at 0
    v_new_quantity := GREATEST(0, COALESCE(v_inv.quantity, 0) + v_adjustment);

    -- Update the inventory item
    UPDATE inventory_items
    SET quantity = v_new_quantity,
        updated_at = NOW()
    WHERE id = v_inv.id;

    -- Append result to JSONB array
    v_results := v_results || jsonb_build_object(
      'productId', v_product_id,
      'newQuantity', v_new_quantity
    );
  END LOOP;

  RETURN v_results;
END;
$$;

COMMENT ON FUNCTION bulk_adjust_inventory IS 'Atomically adjusts inventory quantities for multiple products. Locks all affected rows to prevent races. Floors quantities at 0.';
