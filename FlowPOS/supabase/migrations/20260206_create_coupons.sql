-- =============================================================================
-- Migration: Create Coupons Table
-- Description: Coupon/promo code system for organizations
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Table
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS coupons (
  id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id       UUID        NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  code                  TEXT        NOT NULL,
  name                  TEXT        NOT NULL,
  type                  TEXT        NOT NULL CHECK (type IN ('percentage', 'fixed', 'bogo', 'free_item')),
  value                 INTEGER     NOT NULL DEFAULT 0,
  min_order_amount      INTEGER,
  max_uses              INTEGER,
  used_count            INTEGER     NOT NULL DEFAULT 0,
  valid_from            TIMESTAMPTZ NOT NULL,
  valid_until           TIMESTAMPTZ NOT NULL,
  is_active             BOOLEAN     NOT NULL DEFAULT true,
  applicable_products   UUID[]      DEFAULT '{}',
  applicable_categories UUID[]      DEFAULT '{}',
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(organization_id, code)
);

-- ---------------------------------------------------------------------------
-- 2. Indexes
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_coupons_organization_id
  ON coupons (organization_id);

CREATE INDEX IF NOT EXISTS idx_coupons_code
  ON coupons (organization_id, code);

CREATE INDEX IF NOT EXISTS idx_coupons_active
  ON coupons (organization_id, is_active)
  WHERE is_active = true;

-- ---------------------------------------------------------------------------
-- 3. Row Level Security
-- ---------------------------------------------------------------------------
ALTER TABLE coupons ENABLE ROW LEVEL SECURITY;

-- All org members can view coupons
CREATE POLICY "Org members can view coupons"
  ON coupons FOR SELECT
  USING (organization_id = get_user_organization_id());

-- Only admin/owner/manager can create coupons
CREATE POLICY "Admin/owner/manager can create coupons"
  ON coupons FOR INSERT
  WITH CHECK (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

-- Only admin/owner/manager can update coupons
CREATE POLICY "Admin/owner/manager can update coupons"
  ON coupons FOR UPDATE
  USING (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  )
  WITH CHECK (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

-- Only admin/owner/manager can delete coupons
CREATE POLICY "Admin/owner/manager can delete coupons"
  ON coupons FOR DELETE
  USING (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

-- ---------------------------------------------------------------------------
-- 4. Updated-at trigger
-- ---------------------------------------------------------------------------
CREATE TRIGGER update_coupons_updated_at
  BEFORE UPDATE ON coupons
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();
