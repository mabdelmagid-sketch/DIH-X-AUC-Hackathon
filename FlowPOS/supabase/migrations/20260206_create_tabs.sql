-- =============================================================================
-- Migration: Create Tabs System Tables
-- Description: Bar/restaurant tab management with items and modifiers
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. tabs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tabs (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID        NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  location_id     UUID        REFERENCES locations(id),
  customer_name   TEXT        NOT NULL,
  customer_phone  TEXT,
  card_last_four  TEXT,
  status          TEXT        NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed', 'transferred')),
  opened_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  opened_by       UUID        NOT NULL,
  closed_at       TIMESTAMPTZ,
  closed_by       UUID,
  transferred_to  UUID,
  transferred_at  TIMESTAMPTZ,
  seat_number     INTEGER,
  notes           TEXT,
  pre_auth_amount INTEGER,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 2. tab_items
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tab_items (
  id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  tab_id       UUID        NOT NULL REFERENCES tabs(id) ON DELETE CASCADE,
  product_id   UUID        NOT NULL,
  variant_id   UUID,
  name         TEXT        NOT NULL,
  variant_name TEXT,
  price        INTEGER     NOT NULL,
  quantity     INTEGER     NOT NULL DEFAULT 1,
  notes        TEXT,
  added_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  added_by     UUID        NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 3. tab_item_modifiers
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tab_item_modifiers (
  id           UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
  tab_item_id  UUID    NOT NULL REFERENCES tab_items(id) ON DELETE CASCADE,
  modifier_id  UUID,
  name         TEXT    NOT NULL,
  price        INTEGER NOT NULL DEFAULT 0
);

-- ===========================================================================
-- INDEXES
-- ===========================================================================

-- tabs
CREATE INDEX IF NOT EXISTS idx_tabs_organization_id
  ON tabs (organization_id);

CREATE INDEX IF NOT EXISTS idx_tabs_location_id
  ON tabs (location_id);

CREATE INDEX IF NOT EXISTS idx_tabs_status
  ON tabs (organization_id, status);

CREATE INDEX IF NOT EXISTS idx_tabs_open
  ON tabs (organization_id, status)
  WHERE status = 'open';

CREATE INDEX IF NOT EXISTS idx_tabs_opened_by
  ON tabs (opened_by);

-- tab_items
CREATE INDEX IF NOT EXISTS idx_tab_items_tab_id
  ON tab_items (tab_id);

CREATE INDEX IF NOT EXISTS idx_tab_items_product_id
  ON tab_items (product_id);

-- tab_item_modifiers
CREATE INDEX IF NOT EXISTS idx_tab_item_modifiers_tab_item_id
  ON tab_item_modifiers (tab_item_id);

-- ===========================================================================
-- ROW LEVEL SECURITY
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- tabs RLS
-- ---------------------------------------------------------------------------
ALTER TABLE tabs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Org members can view tabs"
  ON tabs FOR SELECT
  USING (organization_id = get_user_organization_id());

CREATE POLICY "Admin/owner/manager can create tabs"
  ON tabs FOR INSERT
  WITH CHECK (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

CREATE POLICY "Admin/owner/manager can update tabs"
  ON tabs FOR UPDATE
  USING (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  )
  WITH CHECK (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

CREATE POLICY "Admin/owner/manager can delete tabs"
  ON tabs FOR DELETE
  USING (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

-- ---------------------------------------------------------------------------
-- tab_items RLS
-- Note: tab_items does not have organization_id directly.
-- Access is derived through the tabs table.
-- ---------------------------------------------------------------------------
ALTER TABLE tab_items ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Org members can view tab items"
  ON tab_items FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM tabs t
      WHERE t.id = tab_items.tab_id
        AND t.organization_id = get_user_organization_id()
    )
  );

CREATE POLICY "Admin/owner/manager can create tab items"
  ON tab_items FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM tabs t
      WHERE t.id = tab_items.tab_id
        AND t.organization_id = get_user_organization_id()
    )
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

CREATE POLICY "Admin/owner/manager can update tab items"
  ON tab_items FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM tabs t
      WHERE t.id = tab_items.tab_id
        AND t.organization_id = get_user_organization_id()
    )
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM tabs t
      WHERE t.id = tab_items.tab_id
        AND t.organization_id = get_user_organization_id()
    )
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

CREATE POLICY "Admin/owner/manager can delete tab items"
  ON tab_items FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM tabs t
      WHERE t.id = tab_items.tab_id
        AND t.organization_id = get_user_organization_id()
    )
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

-- ---------------------------------------------------------------------------
-- tab_item_modifiers RLS
-- Note: tab_item_modifiers does not have organization_id directly.
-- Access is derived through tab_items -> tabs.
-- ---------------------------------------------------------------------------
ALTER TABLE tab_item_modifiers ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Org members can view tab item modifiers"
  ON tab_item_modifiers FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM tab_items ti
      JOIN tabs t ON t.id = ti.tab_id
      WHERE ti.id = tab_item_modifiers.tab_item_id
        AND t.organization_id = get_user_organization_id()
    )
  );

CREATE POLICY "Admin/owner/manager can create tab item modifiers"
  ON tab_item_modifiers FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM tab_items ti
      JOIN tabs t ON t.id = ti.tab_id
      WHERE ti.id = tab_item_modifiers.tab_item_id
        AND t.organization_id = get_user_organization_id()
    )
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

CREATE POLICY "Admin/owner/manager can update tab item modifiers"
  ON tab_item_modifiers FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM tab_items ti
      JOIN tabs t ON t.id = ti.tab_id
      WHERE ti.id = tab_item_modifiers.tab_item_id
        AND t.organization_id = get_user_organization_id()
    )
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM tab_items ti
      JOIN tabs t ON t.id = ti.tab_id
      WHERE ti.id = tab_item_modifiers.tab_item_id
        AND t.organization_id = get_user_organization_id()
    )
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

CREATE POLICY "Admin/owner/manager can delete tab item modifiers"
  ON tab_item_modifiers FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM tab_items ti
      JOIN tabs t ON t.id = ti.tab_id
      WHERE ti.id = tab_item_modifiers.tab_item_id
        AND t.organization_id = get_user_organization_id()
    )
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

-- ===========================================================================
-- UPDATED-AT TRIGGERS
-- ===========================================================================

CREATE TRIGGER update_tabs_updated_at
  BEFORE UPDATE ON tabs
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();
