/**
 * Partner/reseller role-based permissions
 */

export type PartnerUserRole = "PARTNER_OWNER" | "PARTNER_ADMIN" | "PARTNER_SUPPORT";

export type PartnerPermission =
  | "partner:manage_organizations"
  | "partner:view_organizations"
  | "partner:manage_users"
  | "partner:view_users"
  | "partner:manage_settings"
  | "partner:view_settings"
  | "partner:view_analytics"
  | "partner:manage_billing";

const partnerRolePermissions: Record<PartnerUserRole, PartnerPermission[]> = {
  PARTNER_OWNER: [
    "partner:manage_organizations",
    "partner:view_organizations",
    "partner:manage_users",
    "partner:view_users",
    "partner:manage_settings",
    "partner:view_settings",
    "partner:view_analytics",
    "partner:manage_billing",
  ],
  PARTNER_ADMIN: [
    "partner:manage_organizations",
    "partner:view_organizations",
    "partner:manage_users",
    "partner:view_users",
    "partner:view_settings",
    "partner:view_analytics",
  ],
  PARTNER_SUPPORT: [
    "partner:view_organizations",
    "partner:view_users",
    "partner:view_settings",
  ],
};

export function hasPartnerPermission(
  role: PartnerUserRole,
  permission: PartnerPermission
): boolean {
  return partnerRolePermissions[role]?.includes(permission) ?? false;
}
