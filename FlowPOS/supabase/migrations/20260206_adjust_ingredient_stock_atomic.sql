-- Atomic ingredient stock adjustment with audit trail.
-- Locks the ingredient_stock row (or upserts if not found), adjusts quantity,
-- and inserts an inventory_adjustment record.

CREATE OR REPLACE FUNCTION adjust_ingredient_stock_atomic(
  p_ingredient_id UUID,
  p_location_id UUID,
  p_quantity NUMERIC,
  p_adjustment_type TEXT,
  p_reason TEXT DEFAULT NULL,
  p_notes TEXT DEFAULT NULL,
  p_batch_id UUID DEFAULT NULL,
  p_unit_cost NUMERIC DEFAULT NULL,
  p_user_id UUID DEFAULT NULL,
  p_organization_id UUID DEFAULT NULL
)
RETURNS NUMERIC
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_stock RECORD;
  v_old_quantity NUMERIC;
  v_new_quantity NUMERIC;
  v_stock_id UUID;
BEGIN
  -- Attempt to lock the existing ingredient_stock row
  SELECT *
  INTO v_stock
  FROM ingredient_stock
  WHERE ingredient_id = p_ingredient_id
    AND location_id = p_location_id
  FOR UPDATE;

  IF FOUND THEN
    v_old_quantity := v_stock.quantity;
    v_stock_id := v_stock.id;
  ELSE
    -- Row does not exist; insert it with zero quantity
    INSERT INTO ingredient_stock (ingredient_id, location_id, quantity, created_at, updated_at)
    VALUES (p_ingredient_id, p_location_id, 0, NOW(), NOW())
    RETURNING id, quantity INTO v_stock_id, v_old_quantity;
  END IF;

  -- Calculate new quantity
  v_new_quantity := v_old_quantity + p_quantity;

  -- Prevent negative stock
  IF v_new_quantity < 0 THEN
    RAISE EXCEPTION 'Insufficient stock: current=%, adjustment=%, would result in %',
      v_old_quantity, p_quantity, v_new_quantity
      USING ERRCODE = 'P0004';
  END IF;

  -- Update the stock quantity
  UPDATE ingredient_stock
  SET quantity = v_new_quantity,
      updated_at = NOW(),
      last_restocked_at = CASE
        WHEN p_adjustment_type = 'RECEIVE' THEN NOW()
        ELSE last_restocked_at
      END,
      last_counted_at = CASE
        WHEN p_adjustment_type = 'COUNT' THEN NOW()
        ELSE last_counted_at
      END
  WHERE id = v_stock_id;

  -- Insert audit trail record
  INSERT INTO inventory_adjustments (
    ingredient_id,
    location_id,
    organization_id,
    adjustment_type,
    quantity_before,
    quantity_after,
    quantity_change,
    reason,
    notes,
    batch_id,
    unit_cost,
    total_cost,
    adjusted_by,
    created_at
  ) VALUES (
    p_ingredient_id,
    p_location_id,
    p_organization_id,
    p_adjustment_type::inventory_adjustment_type,
    v_old_quantity,
    v_new_quantity,
    p_quantity,
    p_reason,
    p_notes,
    p_batch_id,
    p_unit_cost,
    CASE WHEN p_unit_cost IS NOT NULL THEN p_unit_cost * ABS(p_quantity) ELSE NULL END,
    p_user_id,
    NOW()
  );

  RETURN v_new_quantity;
END;
$$;

COMMENT ON FUNCTION adjust_ingredient_stock_atomic IS 'Atomically adjusts ingredient stock and creates an audit record. Locks the stock row to prevent races. Raises exception if stock would go negative.';
