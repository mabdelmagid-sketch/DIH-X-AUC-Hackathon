-- Atomic batch disposal (partial or full).
-- Locks the batch, adjusts its quantity, subtracts from ingredient_stock,
-- and creates an audit record.

CREATE OR REPLACE FUNCTION dispose_batch_atomic(
  p_batch_id UUID,
  p_reason TEXT,
  p_quantity NUMERIC DEFAULT NULL,
  p_user_id UUID DEFAULT NULL,
  p_organization_id UUID DEFAULT NULL
)
RETURNS NUMERIC
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_batch RECORD;
  v_dispose_qty NUMERIC;
  v_remaining_qty NUMERIC;
  v_old_stock NUMERIC;
  v_new_stock NUMERIC;
BEGIN
  -- Lock the batch row
  SELECT *
  INTO v_batch
  FROM inventory_batches
  WHERE id = p_batch_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Batch not found: %', p_batch_id
      USING ERRCODE = 'P0002';
  END IF;

  -- Check batch is not already fully disposed
  IF v_batch.disposed_at IS NOT NULL THEN
    RAISE EXCEPTION 'Batch % has already been fully disposed', p_batch_id
      USING ERRCODE = 'P0003';
  END IF;

  -- Determine quantity to dispose
  IF p_quantity IS NULL THEN
    -- Dispose entire remaining batch
    v_dispose_qty := v_batch.quantity;
  ELSE
    IF p_quantity > v_batch.quantity THEN
      RAISE EXCEPTION 'Cannot dispose % units; only % available in batch',
        p_quantity, v_batch.quantity
        USING ERRCODE = 'P0004';
    END IF;
    IF p_quantity <= 0 THEN
      RAISE EXCEPTION 'Disposal quantity must be positive'
        USING ERRCODE = 'P0001';
    END IF;
    v_dispose_qty := p_quantity;
  END IF;

  -- Calculate remaining batch quantity
  v_remaining_qty := v_batch.quantity - v_dispose_qty;

  -- Update batch: reduce quantity, mark as disposed if fully consumed
  IF v_remaining_qty = 0 THEN
    UPDATE inventory_batches
    SET quantity = 0,
        disposed_at = NOW(),
        disposed_reason = p_reason,
        updated_at = NOW()
    WHERE id = p_batch_id;
  ELSE
    UPDATE inventory_batches
    SET quantity = v_remaining_qty,
        updated_at = NOW()
    WHERE id = p_batch_id;
  END IF;

  -- Subtract from ingredient_stock
  SELECT quantity
  INTO v_old_stock
  FROM ingredient_stock
  WHERE ingredient_id = v_batch.ingredient_id
    AND location_id = v_batch.location_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Ingredient stock record not found for ingredient % at location %',
      v_batch.ingredient_id, v_batch.location_id
      USING ERRCODE = 'P0002';
  END IF;

  v_new_stock := GREATEST(0, v_old_stock - v_dispose_qty);

  UPDATE ingredient_stock
  SET quantity = v_new_stock,
      updated_at = NOW()
  WHERE ingredient_id = v_batch.ingredient_id
    AND location_id = v_batch.location_id;

  -- Insert inventory adjustment audit record
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
    v_batch.ingredient_id,
    v_batch.location_id,
    p_organization_id,
    'WASTE'::inventory_adjustment_type,
    v_old_stock,
    v_new_stock,
    -v_dispose_qty,
    p_reason,
    NULL,
    p_batch_id,
    v_batch.cost_per_unit,
    CASE WHEN v_batch.cost_per_unit IS NOT NULL THEN v_batch.cost_per_unit * v_dispose_qty ELSE NULL END,
    p_user_id,
    NOW()
  );

  RETURN v_remaining_qty;
END;
$$;

COMMENT ON FUNCTION dispose_batch_atomic IS 'Atomically disposes a batch (partial or full), subtracts from ingredient stock, and creates a WASTE audit record. Locks both batch and stock rows.';
