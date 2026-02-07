-- Bulk update sort_order for products or categories in a single transaction.
-- Uses a whitelist to prevent SQL injection via dynamic table names.

CREATE OR REPLACE FUNCTION bulk_update_sort_order(
  p_table_name TEXT,
  p_items JSONB,
  p_organization_id UUID
)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_item JSONB;
  v_count INTEGER := 0;
  v_rows_affected INTEGER;
BEGIN
  -- Whitelist allowed table names to prevent SQL injection
  IF p_table_name NOT IN ('products', 'categories') THEN
    RAISE EXCEPTION 'Invalid table name: %. Allowed: products, categories', p_table_name
      USING ERRCODE = 'P0001';
  END IF;

  -- Validate p_items is a non-empty array
  IF p_items IS NULL OR jsonb_array_length(p_items) = 0 THEN
    RAISE EXCEPTION 'p_items must be a non-empty JSON array'
      USING ERRCODE = 'P0001';
  END IF;

  -- Loop through each item and update sort_order
  FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
  LOOP
    EXECUTE format(
      'UPDATE %I SET sort_order = $1, updated_at = NOW() WHERE id = $2 AND organization_id = $3',
      p_table_name
    )
    USING (v_item->>'sortOrder')::INTEGER,
          (v_item->>'id')::UUID,
          p_organization_id;

    GET DIAGNOSTICS v_rows_affected = ROW_COUNT;
    v_count := v_count + v_rows_affected;
  END LOOP;

  RETURN v_count;
END;
$$;

COMMENT ON FUNCTION bulk_update_sort_order IS 'Atomically updates sort_order for multiple products or categories. Table name is whitelisted to prevent SQL injection.';
