-- =============================================================================
-- Migration: Create Loyalty System Tables
-- Description: Loyalty tiers, rewards, members, point transactions,
--              store credit transactions, and punch card progress
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. loyalty_tiers
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS loyalty_tiers (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id   UUID        NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  name              TEXT        NOT NULL,
  min_points        INTEGER     NOT NULL DEFAULT 0,
  points_multiplier NUMERIC     NOT NULL DEFAULT 1.0,
  perks             TEXT[]      DEFAULT '{}',
  color             TEXT,
  sort_order        INTEGER     NOT NULL DEFAULT 0,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 2. loyalty_rewards
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS loyalty_rewards (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID        NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  name            TEXT        NOT NULL,
  description     TEXT,
  points_cost     INTEGER     NOT NULL DEFAULT 0,
  type            TEXT        NOT NULL CHECK (type IN (
                    'discount_percentage', 'discount_fixed', 'free_item',
                    'store_credit', 'punch_card'
                  )),
  value           NUMERIC,
  is_active       BOOLEAN     NOT NULL DEFAULT true,
  buy_quantity    INTEGER,
  free_quantity   INTEGER,
  category_id     UUID,
  product_id      UUID,
  spend_amount    INTEGER,
  discount_type   TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 3. loyalty_members
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS loyalty_members (
  id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id       UUID        NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  customer_id           UUID        REFERENCES customers(id),
  customer_name         TEXT,
  customer_email        TEXT,
  customer_phone        TEXT,
  points                INTEGER     NOT NULL DEFAULT 0,
  total_points_earned   INTEGER     NOT NULL DEFAULT 0,
  total_points_redeemed INTEGER     NOT NULL DEFAULT 0,
  tier_id               UUID        REFERENCES loyalty_tiers(id),
  joined_at             TIMESTAMPTZ,
  last_activity         TIMESTAMPTZ,
  store_credit          INTEGER     NOT NULL DEFAULT 0,
  total_credit_issued   INTEGER     NOT NULL DEFAULT 0,
  total_credit_used     INTEGER     NOT NULL DEFAULT 0,
  birthday              DATE,
  anniversary           DATE,
  tags                  TEXT[]      DEFAULT '{}',
  total_spent           INTEGER     NOT NULL DEFAULT 0,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 4. point_transactions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS point_transactions (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID        NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  member_id       UUID        NOT NULL REFERENCES loyalty_members(id) ON DELETE CASCADE,
  type            TEXT        NOT NULL CHECK (type IN ('earn', 'redeem', 'expire', 'adjust')),
  points          INTEGER     NOT NULL,
  description     TEXT,
  order_id        UUID,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 5. store_credit_transactions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS store_credit_transactions (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID        NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  member_id       UUID        NOT NULL REFERENCES loyalty_members(id) ON DELETE CASCADE,
  type            TEXT        NOT NULL CHECK (type IN ('issue', 'use', 'refund', 'adjust', 'expire')),
  amount          INTEGER     NOT NULL,
  balance         INTEGER     NOT NULL,
  description     TEXT,
  order_id        UUID,
  issued_by       UUID,
  expires_at      TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 6. punch_card_progress
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS punch_card_progress (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  member_id       UUID        NOT NULL REFERENCES loyalty_members(id) ON DELETE CASCADE,
  reward_id       UUID        NOT NULL REFERENCES loyalty_rewards(id) ON DELETE CASCADE,
  current_punches INTEGER     NOT NULL DEFAULT 0,
  completed       BOOLEAN     NOT NULL DEFAULT false,
  completed_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ===========================================================================
-- INDEXES
-- ===========================================================================

-- loyalty_tiers
CREATE INDEX IF NOT EXISTS idx_loyalty_tiers_organization_id
  ON loyalty_tiers (organization_id);

CREATE INDEX IF NOT EXISTS idx_loyalty_tiers_sort_order
  ON loyalty_tiers (organization_id, sort_order);

-- loyalty_rewards
CREATE INDEX IF NOT EXISTS idx_loyalty_rewards_organization_id
  ON loyalty_rewards (organization_id);

CREATE INDEX IF NOT EXISTS idx_loyalty_rewards_active
  ON loyalty_rewards (organization_id, is_active)
  WHERE is_active = true;

CREATE INDEX IF NOT EXISTS idx_loyalty_rewards_type
  ON loyalty_rewards (organization_id, type);

-- loyalty_members
CREATE INDEX IF NOT EXISTS idx_loyalty_members_organization_id
  ON loyalty_members (organization_id);

CREATE INDEX IF NOT EXISTS idx_loyalty_members_customer_id
  ON loyalty_members (organization_id, customer_id);

CREATE INDEX IF NOT EXISTS idx_loyalty_members_tier_id
  ON loyalty_members (tier_id);

CREATE INDEX IF NOT EXISTS idx_loyalty_members_phone
  ON loyalty_members (organization_id, customer_phone);

CREATE INDEX IF NOT EXISTS idx_loyalty_members_email
  ON loyalty_members (organization_id, customer_email);

-- point_transactions
CREATE INDEX IF NOT EXISTS idx_point_transactions_organization_id
  ON point_transactions (organization_id);

CREATE INDEX IF NOT EXISTS idx_point_transactions_member_id
  ON point_transactions (member_id);

CREATE INDEX IF NOT EXISTS idx_point_transactions_order_id
  ON point_transactions (order_id);

CREATE INDEX IF NOT EXISTS idx_point_transactions_created_at
  ON point_transactions (member_id, created_at DESC);

-- store_credit_transactions
CREATE INDEX IF NOT EXISTS idx_store_credit_txns_organization_id
  ON store_credit_transactions (organization_id);

CREATE INDEX IF NOT EXISTS idx_store_credit_txns_member_id
  ON store_credit_transactions (member_id);

CREATE INDEX IF NOT EXISTS idx_store_credit_txns_order_id
  ON store_credit_transactions (order_id);

CREATE INDEX IF NOT EXISTS idx_store_credit_txns_created_at
  ON store_credit_transactions (member_id, created_at DESC);

-- punch_card_progress
CREATE INDEX IF NOT EXISTS idx_punch_card_progress_member_id
  ON punch_card_progress (member_id);

CREATE INDEX IF NOT EXISTS idx_punch_card_progress_reward_id
  ON punch_card_progress (reward_id);

CREATE INDEX IF NOT EXISTS idx_punch_card_progress_active
  ON punch_card_progress (member_id, reward_id)
  WHERE completed = false;

-- ===========================================================================
-- ROW LEVEL SECURITY
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- loyalty_tiers RLS
-- ---------------------------------------------------------------------------
ALTER TABLE loyalty_tiers ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Org members can view loyalty tiers"
  ON loyalty_tiers FOR SELECT
  USING (organization_id = get_user_organization_id());

CREATE POLICY "Admin/owner/manager can create loyalty tiers"
  ON loyalty_tiers FOR INSERT
  WITH CHECK (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

CREATE POLICY "Admin/owner/manager can update loyalty tiers"
  ON loyalty_tiers FOR UPDATE
  USING (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  )
  WITH CHECK (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

CREATE POLICY "Admin/owner/manager can delete loyalty tiers"
  ON loyalty_tiers FOR DELETE
  USING (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

-- ---------------------------------------------------------------------------
-- loyalty_rewards RLS
-- ---------------------------------------------------------------------------
ALTER TABLE loyalty_rewards ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Org members can view loyalty rewards"
  ON loyalty_rewards FOR SELECT
  USING (organization_id = get_user_organization_id());

CREATE POLICY "Admin/owner/manager can create loyalty rewards"
  ON loyalty_rewards FOR INSERT
  WITH CHECK (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

CREATE POLICY "Admin/owner/manager can update loyalty rewards"
  ON loyalty_rewards FOR UPDATE
  USING (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  )
  WITH CHECK (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

CREATE POLICY "Admin/owner/manager can delete loyalty rewards"
  ON loyalty_rewards FOR DELETE
  USING (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

-- ---------------------------------------------------------------------------
-- loyalty_members RLS
-- ---------------------------------------------------------------------------
ALTER TABLE loyalty_members ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Org members can view loyalty members"
  ON loyalty_members FOR SELECT
  USING (organization_id = get_user_organization_id());

CREATE POLICY "Admin/owner/manager can create loyalty members"
  ON loyalty_members FOR INSERT
  WITH CHECK (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

CREATE POLICY "Admin/owner/manager can update loyalty members"
  ON loyalty_members FOR UPDATE
  USING (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  )
  WITH CHECK (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

CREATE POLICY "Admin/owner/manager can delete loyalty members"
  ON loyalty_members FOR DELETE
  USING (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

-- ---------------------------------------------------------------------------
-- point_transactions RLS
-- ---------------------------------------------------------------------------
ALTER TABLE point_transactions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Org members can view point transactions"
  ON point_transactions FOR SELECT
  USING (organization_id = get_user_organization_id());

CREATE POLICY "Admin/owner/manager can create point transactions"
  ON point_transactions FOR INSERT
  WITH CHECK (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

CREATE POLICY "Admin/owner/manager can update point transactions"
  ON point_transactions FOR UPDATE
  USING (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  )
  WITH CHECK (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

CREATE POLICY "Admin/owner/manager can delete point transactions"
  ON point_transactions FOR DELETE
  USING (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

-- ---------------------------------------------------------------------------
-- store_credit_transactions RLS
-- ---------------------------------------------------------------------------
ALTER TABLE store_credit_transactions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Org members can view store credit transactions"
  ON store_credit_transactions FOR SELECT
  USING (organization_id = get_user_organization_id());

CREATE POLICY "Admin/owner/manager can create store credit transactions"
  ON store_credit_transactions FOR INSERT
  WITH CHECK (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

CREATE POLICY "Admin/owner/manager can update store credit transactions"
  ON store_credit_transactions FOR UPDATE
  USING (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  )
  WITH CHECK (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

CREATE POLICY "Admin/owner/manager can delete store credit transactions"
  ON store_credit_transactions FOR DELETE
  USING (
    organization_id = get_user_organization_id()
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

-- ---------------------------------------------------------------------------
-- punch_card_progress RLS
-- Note: punch_card_progress does not have organization_id directly.
-- Access is derived through the loyalty_members table.
-- ---------------------------------------------------------------------------
ALTER TABLE punch_card_progress ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Org members can view punch card progress"
  ON punch_card_progress FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM loyalty_members lm
      WHERE lm.id = punch_card_progress.member_id
        AND lm.organization_id = get_user_organization_id()
    )
  );

CREATE POLICY "Admin/owner/manager can create punch card progress"
  ON punch_card_progress FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM loyalty_members lm
      WHERE lm.id = punch_card_progress.member_id
        AND lm.organization_id = get_user_organization_id()
    )
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

CREATE POLICY "Admin/owner/manager can update punch card progress"
  ON punch_card_progress FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM loyalty_members lm
      WHERE lm.id = punch_card_progress.member_id
        AND lm.organization_id = get_user_organization_id()
    )
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM loyalty_members lm
      WHERE lm.id = punch_card_progress.member_id
        AND lm.organization_id = get_user_organization_id()
    )
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

CREATE POLICY "Admin/owner/manager can delete punch card progress"
  ON punch_card_progress FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM loyalty_members lm
      WHERE lm.id = punch_card_progress.member_id
        AND lm.organization_id = get_user_organization_id()
    )
    AND get_user_role() IN ('OWNER', 'ADMIN', 'MANAGER')
  );

-- ===========================================================================
-- UPDATED-AT TRIGGERS
-- ===========================================================================

CREATE TRIGGER update_loyalty_tiers_updated_at
  BEFORE UPDATE ON loyalty_tiers
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_loyalty_rewards_updated_at
  BEFORE UPDATE ON loyalty_rewards
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_loyalty_members_updated_at
  BEFORE UPDATE ON loyalty_members
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_punch_card_progress_updated_at
  BEFORE UPDATE ON punch_card_progress
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();
