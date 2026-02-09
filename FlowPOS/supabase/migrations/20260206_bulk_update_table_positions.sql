-- Bulk update table positions atomically.
-- Updates pos_x, pos_y, and optionally width and height for multiple tables.

CREATE OR REPLACE FUNCTION bulk_update_table_positions(
  p_tables JSONB,
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
  v_width INTEGER;
  v_height INTEGER;
BEGIN
  -- Validate p_tables is a non-empty array
  IF p_tables IS NULL OR jsonb_array_length(p_tables) = 0 THEN
    RAISE EXCEPTION 'p_tables must be a non-empty JSON array'
      USING ERRCODE = 'P0001';
  END IF;

  FOR v_item IN SELECT * FROM jsonb_array_elements(p_tables)
  LOOP
    -- Extract optional width and height
    v_width := (v_item->>'width')::INTEGER;
    v_height := (v_item->>'height')::INTEGER;

    IF v_width IS NOT NULL AND v_height IS NOT NULL THEN
      -- Update position and dimensions
      UPDATE tables
      SET pos_x = (v_item->>'posX')::INTEGER,
          pos_y = (v_item->>'posY')::INTEGER,
          width = v_width,
          height = v_height,
          updated_at = NOW()
      WHERE id = (v_item->>'id')::UUID
        AND location_id IN (
          SELECT id FROM locations WHERE organization_id = p_organization_id
        );
    ELSIF v_width IS NOT NULL THEN
      -- Update position and width only
      UPDATE tables
      SET pos_x = (v_item->>'posX')::INTEGER,
          pos_y = (v_item->>'posY')::INTEGER,
          width = v_width,
          updated_at = NOW()
      WHERE id = (v_item->>'id')::UUID
        AND location_id IN (
          SELECT id FROM locations WHERE organization_id = p_organization_id
        );
    ELSIF v_height IS NOT NULL THEN
      -- Update position and height only
      UPDATE tables
      SET pos_x = (v_item->>'posX')::INTEGER,
          pos_y = (v_item->>'posY')::INTEGER,
          height = v_height,
          updated_at = NOW()
      WHERE id = (v_item->>'id')::UUID
        AND location_id IN (
          SELECT id FROM locations WHERE organization_id = p_organization_id
        );
    ELSE
      -- Update position only
      UPDATE tables
      SET pos_x = (v_item->>'posX')::INTEGER,
          pos_y = (v_item->>'posY')::INTEGER,
          updated_at = NOW()
      WHERE id = (v_item->>'id')::UUID
        AND location_id IN (
          SELECT id FROM locations WHERE organization_id = p_organization_id
        );
    END IF;

    GET DIAGNOSTICS v_rows_affected = ROW_COUNT;
    v_count := v_count + v_rows_affected;
  END LOOP;

  RETURN v_count;
END;
$$;

COMMENT ON FUNCTION bulk_update_table_positions IS 'Atomically updates positions (and optionally dimensions) for multiple tables. Verifies tables belong to the organization via location.';
