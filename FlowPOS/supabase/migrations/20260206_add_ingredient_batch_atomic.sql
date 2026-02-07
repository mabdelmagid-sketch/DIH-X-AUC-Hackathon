-- Atomic ingredient batch addition.
-- Inserts a new inventory_batch, upserts ingredient_stock, and creates an audit record.

CREATE OR REPLACE FUNCTION add_ingredient_batch_atomic(
  p_ingredient_id UUID,
  p_location_id UUID,
  p_quantity NUMERIC,
  p_batch_number TEXT DEFAULT NULL,
  p_cost_per_unit NUMERIC DEFAULT NULL,
  p_expiry_date TIMESTAMPTZ DEFAULT NULL,
  p_supplier_id UUID DEFAULT NULL,
  p_purchase_order_id UUID DEFAULT NULL,
  p_notes TEXT DEFAULT NULL,
  p_user_id UUID DEFAULT NULL,
  p_organization_id UUID DEFAULT NULL
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_batch_id UUID;
  v_old_quantity NUMERIC;
  v_new_quantity NUMERIC;
BEGIN
  -- Insert new inventory batch
  INSERT INTO inventory_batches (
    ingredient_id,
    location_id,
    batch_number,
    quantity,
    initial_quantity,
    cost_per_unit,
    expiry_date,
    received_date,
    supplier_id,
    purchase_order_id,
    notes,
    created_at,
    updated_at
  ) VALUES (
    p_ingredient_id,
    p_location_id,
    p_batch_number,
    p_quantity,
    p_quantity,
    p_cost_per_unit,
    p_expiry_date,
    NOW(),
    p_supplier_id,
    p_purchase_order_id,
    p_notes,
    NOW(),
    NOW()
  )
  RETURNING id INTO v_batch_id;

  -- Upsert ingredient_stock: insert or update quantity
  INSERT INTO ingredient_stock (ingredient_id, location_id, quantity, last_restocked_at, created_at, updated_at)
  VALUES (p_ingredient_id, p_location_id, p_quantity, NOW(), NOW(), NOW())
  ON CONFLICT (ingredient_id, location_id) DO UPDATE
  SET quantity = ingredient_stock.quantity + EXCLUDED.quantity,
      last_restocked_at = NOW(),
      updated_at = NOW()
  RETURNING quantity - p_quantity, quantity
  INTO v_old_quantity, v_new_quantity;

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
    p_ingredient_id,
    p_location_id,
    p_organization_id,
    'RECEIVE'::inventory_adjustment_type,
    v_old_quantity,
    v_new_quantity,
    p_quantity,
    'Batch received',
    p_notes,
    v_batch_id,
    p_cost_per_unit,
    CASE WHEN p_cost_per_unit IS NOT NULL THEN p_cost_per_unit * p_quantity ELSE NULL END,
    p_user_id,
    NOW()
  );

  RETURN v_batch_id;
END;
$$;

COMMENT ON FUNCTION add_ingredient_batch_atomic IS 'Atomically adds a new ingredient batch, upserts stock quantity, and creates an audit record.';
