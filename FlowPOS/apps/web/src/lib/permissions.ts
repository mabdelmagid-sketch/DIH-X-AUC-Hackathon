/**
 * Role-based permissions system
 * Uses colon-separated format: "entity:action"
 */

export type UserRole = "OWNER" | "ADMIN" | "MANAGER" | "CASHIER" | "WAITER" | "KITCHEN";

export type Permission =
  // POS
  | "pos:access"
  | "pos:void"
  | "pos:refund"
  // Products
  | "products:view"
  | "products:edit"
  | "products:delete"
  // Orders
  | "orders:view"
  | "orders:create"
  | "orders:edit"
  // Inventory
  | "inventory:view"
  | "inventory:adjust"
  // Customers
  | "customers:view"
  | "customers:edit"
  // Employees
  | "employees:view"
  | "employees:edit"
  | "employees:create"
  | "employees:delete"
  // Reports
  | "reports:view"
  // Tables
  | "tables:view"
  | "tables:manage"
  // Kitchen
  | "kitchen:view"
  | "kitchen:bump"
  // Settings
  | "settings:view"
  | "settings:edit"
  // Loyalty
  | "loyalty:view"
  | "loyalty:manage";

const rolePermissions: Record<UserRole, Permission[]> = {
  OWNER: [
    "pos:access", "pos:void", "pos:refund",
    "products:view", "products:edit", "products:delete",
    "orders:view", "orders:create", "orders:edit",
    "inventory:view", "inventory:adjust",
    "customers:view", "customers:edit",
    "employees:view", "employees:edit", "employees:create", "employees:delete",
    "reports:view",
    "tables:view", "tables:manage",
    "kitchen:view", "kitchen:bump",
    "settings:view", "settings:edit",
    "loyalty:view", "loyalty:manage",
  ],
  ADMIN: [
    "pos:access", "pos:void", "pos:refund",
    "products:view", "products:edit", "products:delete",
    "orders:view", "orders:create", "orders:edit",
    "inventory:view", "inventory:adjust",
    "customers:view", "customers:edit",
    "employees:view", "employees:edit", "employees:create", "employees:delete",
    "reports:view",
    "tables:view", "tables:manage",
    "kitchen:view", "kitchen:bump",
    "settings:view", "settings:edit",
    "loyalty:view", "loyalty:manage",
  ],
  MANAGER: [
    "pos:access", "pos:void", "pos:refund",
    "products:view", "products:edit",
    "orders:view", "orders:create", "orders:edit",
    "inventory:view", "inventory:adjust",
    "customers:view", "customers:edit",
    "employees:view", "employees:edit", "employees:create",
    "reports:view",
    "tables:view", "tables:manage",
    "kitchen:view", "kitchen:bump",
    "settings:view",
    "loyalty:view", "loyalty:manage",
  ],
  CASHIER: [
    "pos:access",
    "products:view",
    "orders:view", "orders:create", "orders:edit",
    "inventory:view",
    "customers:view",
    "tables:view",
    "loyalty:view",
  ],
  WAITER: [
    "pos:access",
    "products:view",
    "orders:view", "orders:create", "orders:edit",
    "customers:view",
    "tables:view", "tables:manage",
    "kitchen:view",
  ],
  KITCHEN: [
    "orders:view",
    "kitchen:view", "kitchen:bump",
  ],
};

export function hasPermission(role: UserRole, permission: Permission): boolean {
  return rolePermissions[role]?.includes(permission) ?? false;
}

export function hasAnyPermission(role: UserRole, permissions: Permission[]): boolean {
  return permissions.some((p) => hasPermission(role, p));
}

export function hasAllPermissions(role: UserRole, permissions: Permission[]): boolean {
  return permissions.every((p) => hasPermission(role, p));
}

export function getRolePermissions(role: UserRole): Permission[] {
  return rolePermissions[role] ?? [];
}
