-- Server-side inventory filtering function.
-- Replaces client-side filtering with database-level WHERE clauses, ILIKE search, and LIMIT/OFFSET.

CREATE OR REPLACE FUNCTION get_inventory_items(
  p_organization_id UUID,
  p_location_id UUID DEFAULT NULL,
  p_product_id UUID DEFAULT NULL,
  p_low_stock_only BOOLEAN DEFAULT FALSE,
  p_search TEXT DEFAULT NULL,
  p_limit INTEGER DEFAULT 50,
  p_offset INTEGER DEFAULT 0
)
RETURNS TABLE (
  id UUID,
  product_id UUID,
  location_id UUID,
  quantity INTEGER,
  low_stock INTEGER,
  updated_at TIMESTAMPTZ,
  product_name TEXT,
  product_sku TEXT,
  product_barcode TEXT,
  product_price INTEGER,
  product_image TEXT,
  product_is_active BOOLEAN,
  location_name TEXT,
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
      ii.id,
      ii.product_id,
      ii.location_id,
      ii.quantity,
      ii.low_stock,
      ii.updated_at,
      p.name AS product_name,
      p.sku AS product_sku,
      p.barcode AS product_barcode,
      p.price AS product_price,
      p.image AS product_image,
      p.is_active AS product_is_active,
      l.name AS location_name
    FROM inventory_items ii
    JOIN products p ON p.id = ii.product_id
    JOIN locations l ON l.id = ii.location_id
    WHERE p.organization_id = p_organization_id
      AND p.track_inventory = true
      AND (p_location_id IS NULL OR ii.location_id = p_location_id)
      AND (p_product_id IS NULL OR ii.product_id = p_product_id)
      AND (NOT p_low_stock_only OR ii.quantity <= ii.low_stock)
      AND (
        p_search IS NULL
        OR p.name ILIKE '%' || p_search || '%'
        OR p.sku ILIKE '%' || p_search || '%'
      )
  )
  SELECT
    f.id,
    f.product_id,
    f.location_id,
    f.quantity,
    f.low_stock,
    f.updated_at,
    f.product_name,
    f.product_sku,
    f.product_barcode,
    f.product_price,
    f.product_image,
    f.product_is_active,
    f.location_name,
    COUNT(*) OVER () AS total_count
  FROM filtered f
  ORDER BY f.product_name
  LIMIT p_limit
  OFFSET p_offset;
END;
$$;

COMMENT ON FUNCTION get_inventory_items IS 'Server-side filtered inventory list with search, low stock filter, and pagination. Replaces client-side filtering for better performance.';
