-- Atomic employee update: updates both employees and users tables in a single transaction.
-- If any step fails, the entire operation is rolled back automatically.

CREATE OR REPLACE FUNCTION update_employee_atomic(
  p_employee_id UUID,
  p_name TEXT DEFAULT NULL,
  p_role TEXT DEFAULT NULL,
  p_location_id UUID DEFAULT NULL,
  p_pin TEXT DEFAULT NULL,
  p_hourly_rate NUMERIC DEFAULT NULL,
  p_is_active BOOLEAN DEFAULT NULL,
  p_organization_id UUID DEFAULT NULL
)
RETURNS SETOF employees
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_employee RECORD;
BEGIN
  -- Lock the employee row and verify it belongs to the organization
  SELECT e.*
  INTO v_employee
  FROM employees e
  JOIN users u ON u.id = e.user_id
  WHERE e.id = p_employee_id
    AND u.organization_id = p_organization_id
    AND e.deleted_at IS NULL
  FOR UPDATE OF e;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Employee not found or does not belong to organization'
      USING ERRCODE = 'P0002';
  END IF;

  -- Update users.name if provided
  IF p_name IS NOT NULL THEN
    UPDATE users
    SET name = p_name,
        updated_at = NOW()
    WHERE id = v_employee.user_id;
  END IF;

  -- Update users.role if provided
  IF p_role IS NOT NULL THEN
    UPDATE users
    SET role = p_role::user_role,
        updated_at = NOW()
    WHERE id = v_employee.user_id;
  END IF;

  -- Update employees.location_id if provided
  IF p_location_id IS NOT NULL THEN
    UPDATE employees
    SET location_id = p_location_id,
        updated_at = NOW()
    WHERE id = p_employee_id;
  END IF;

  -- Update employees.pin if provided (already hashed by app)
  IF p_pin IS NOT NULL THEN
    UPDATE employees
    SET pin = p_pin,
        updated_at = NOW()
    WHERE id = p_employee_id;
  END IF;

  -- Update employees.hourly_rate if provided
  IF p_hourly_rate IS NOT NULL THEN
    UPDATE employees
    SET hourly_rate = p_hourly_rate,
        updated_at = NOW()
    WHERE id = p_employee_id;
  END IF;

  -- Update is_active on both tables if provided
  IF p_is_active IS NOT NULL THEN
    UPDATE employees
    SET is_active = p_is_active,
        updated_at = NOW()
    WHERE id = p_employee_id;

    UPDATE users
    SET is_active = p_is_active,
        updated_at = NOW()
    WHERE id = v_employee.user_id;
  END IF;

  -- Return the updated employee row
  RETURN QUERY
    SELECT *
    FROM employees
    WHERE id = p_employee_id;
END;
$$;

COMMENT ON FUNCTION update_employee_atomic IS 'Atomically updates employee and related user records. Locks the employee row to prevent concurrent modifications. Raises exception on failure to auto-rollback.';
