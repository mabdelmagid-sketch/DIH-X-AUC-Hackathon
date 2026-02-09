-- Atomic employee soft-delete: marks employee as deleted and deactivates the user.
-- If any step fails, the entire operation is rolled back automatically.

CREATE OR REPLACE FUNCTION delete_employee_atomic(
  p_employee_id UUID,
  p_organization_id UUID
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_employee RECORD;
BEGIN
  -- Lock employee row and verify it belongs to the organization
  SELECT e.id, e.user_id
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

  -- Soft-delete the employee
  UPDATE employees
  SET deleted_at = NOW(),
      is_active = false,
      updated_at = NOW()
  WHERE id = p_employee_id;

  -- Deactivate the user
  UPDATE users
  SET is_active = false,
      updated_at = NOW()
  WHERE id = v_employee.user_id;

  RETURN p_employee_id;
END;
$$;

COMMENT ON FUNCTION delete_employee_atomic IS 'Atomically soft-deletes an employee and deactivates the related user. Locks the employee row to prevent concurrent modifications.';
