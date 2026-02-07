-- Server-side ingredients list with stock level filtering.
-- Handles low stock filtering at the database level instead of post-fetch in JS.

CREATE OR REPLACE FUNCTION get_ingredients_with_stock(
  p_organization_id UUID,
  p_location_id UUID DEFAULT NULL,
  p_category TEXT DEFAULT NULL,
  p_supplier_id UUID DEFAULT NULL,
  p_is_active BOOLEAN DEFAULT NULL,
  p_low_stock_only BOOLEAN DEFAULT FALSE,
  p_search TEXT DEFAULT NULL,
  p_limit INTEGER DEFAULT 50,
  p_offset INTEGER DEFAULT 0
)
RETURNS TABLE (
  id UUID,
  name TEXT,
  description TEXT,
  sku TEXT,
  barcode TEXT,
  category TEXT,
  unit TEXT,
  cost_per_unit INTEGER,
  min_stock_level NUMERIC,
  reorder_quantity NUMERIC,
  supplier_id UUID,
  storage_instructions TEXT,
  allergens JSONB,
  is_active BOOLEAN,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  supplier_name TEXT,
  current_stock NUMERIC,
  total_count BIGINT
)
LANGUAGE plpgsql
SECURITY DEFINER
STABLE
AS $$
BEGIN
  RETURN QUERY
  WITH filtered AS (
    SELECT
      i.id,
      i.name,
      i.description,
      i.sku,
      i.barcode,
      i.category::TEXT,
      i.unit::TEXT,
      i.cost_per_unit,
      i.min_stock_level,
      i.reorder_quantity,
      i.supplier_id,
      i.storage_instructions,
      i.allergens,
      i.is_active,
      i.created_at,
      i.updated_at,
      s.name AS supplier_name,
      COALESCE(ist.quantity, 0) AS current_stock
    FROM ingredients i
    LEFT JOIN suppliers s ON s.id = i.supplier_id
    LEFT JOIN ingredient_stock ist ON ist.ingredient_id = i.id
      AND (p_location_id IS NULL OR ist.location_id = p_location_id)
    WHERE i.organization_id = p_organization_id
      AND i.deleted_at IS NULL
      AND (p_category IS NULL OR i.category::TEXT = p_category)
      AND (p_supplier_id IS NULL OR i.supplier_id = p_supplier_id)
      AND (p_is_active IS NULL OR i.is_active = p_is_active)
      AND (
        p_search IS NULL
        OR i.name ILIKE '%' || p_search || '%'
        OR i.sku ILIKE '%' || p_search || '%'
        OR i.barcode ILIKE '%' || p_search || '%'
      )
      AND (
        NOT p_low_stock_only
        OR COALESCE(ist.quantity, 0) <= COALESCE(i.min_stock_level, 0)
      )
  )
  SELECT
    f.id,
    f.name,
    f.description,
    f.sku,
    f.barcode,
    f.category,
    f.unit,
    f.cost_per_unit,
    f.min_stock_level,
    f.reorder_quantity,
    f.supplier_id,
    f.storage_instructions,
    f.allergens,
    f.is_active,
    f.created_at,
    f.updated_at,
    f.supplier_name,
    f.current_stock,
    COUNT(*) OVER () AS total_count
  FROM filtered f
  ORDER BY f.name
  LIMIT p_limit
  OFFSET p_offset;
END;
$$;

COMMENT ON FUNCTION get_ingredients_with_stock IS 'Server-side filtered ingredients list with stock levels and low stock filtering. Handles cross-table low stock comparison at DB level.';
