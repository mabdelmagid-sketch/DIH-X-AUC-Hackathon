-- Migration: Hash all existing plaintext PINs using pgcrypto
-- This converts any PINs that are NOT already bcrypt hashes (don't start with '$2')
-- After this migration, the plaintext fallback in verifyPinHash() can be removed

-- Ensure pgcrypto extension is available
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Hash all plaintext PINs (those not starting with '$2')
UPDATE employees
SET pin = crypt(pin, gen_salt('bf', 10))
WHERE pin IS NOT NULL
  AND pin != ''
  AND pin NOT LIKE '$2%';
