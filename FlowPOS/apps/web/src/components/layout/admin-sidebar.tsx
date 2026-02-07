"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import { Icon, LanguageSwitcher } from "@/components/ui";

const adminNavItems = [
  { labelKey: "organizations", icon: "business", href: "/admin/organizations" },
  { labelKey: "users", icon: "group", href: "/admin/users" },
  { labelKey: "systemTitle", icon: "settings", href: "/admin/system" },
  { labelKey: "signupRequests", icon: "how_to_reg", href: "/admin/signup-requests" },
  { labelKey: "partners", icon: "handshake", href: "/admin/partners" },
  { labelKey: "auditLogs", icon: "history", href: "/admin/audit-logs" },
];

interface AdminSidebarProps {
  userName?: string;
  userEmail?: string;
}

export function AdminSidebar({
  userName = "Admin",
  userEmail = "admin@flowpos.com",
}: AdminSidebarProps) {
  const pathname = usePathname();
  const t = useTranslations("admin");
  const tc = useTranslations("common");
  const tn = useTranslations("nav");

  return (
    <aside className="flex flex-col w-[280px] h-full bg-[var(--sidebar)] border-e border-[var(--sidebar-border)] shrink-0">
      {/* Logo */}
      <div className="flex items-center h-[88px] px-8">
        <span className="text-lg font-brand font-bold text-[var(--primary)]">
          {tc("flowPos")}
        </span>
      </div>

      {/* Section Label */}
      <div className="px-8 pb-2">
        <p className="text-sm font-brand text-[var(--sidebar-foreground)]">
          {tn("platformAdmin")}
        </p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-4">
        {adminNavItems.map((item) => {
          const isActive = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-4 px-4 py-1.5 rounded-full",
                "text-sm font-body transition-colors",
                isActive
                  ? "bg-[var(--sidebar-accent)] text-[var(--sidebar-accent-foreground)] font-medium"
                  : "text-[var(--sidebar-foreground)] hover:bg-[var(--sidebar-accent)] hover:text-[var(--sidebar-accent-foreground)]"
              )}
            >
              <Icon
                name={item.icon}
                size={24}
                className={
                  isActive
                    ? "text-[var(--sidebar-accent-foreground)]"
                    : "text-[var(--sidebar-foreground)]"
                }
              />
              <span>{t(item.labelKey)}</span>
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-8 py-6 border-t border-[var(--sidebar-border)]">
        <div className="flex items-center justify-between mb-3">
          <LanguageSwitcher />
        </div>
        <div className="flex items-center gap-2">
          <div className="flex-1 min-w-0">
            <p className="text-sm font-body font-medium text-[var(--foreground)] truncate">
              {userName}
            </p>
            <p className="text-xs font-body text-[var(--muted-foreground)] truncate">
              {userEmail}
            </p>
          </div>
          <Icon
            name="keyboard_arrow_down"
            size={24}
            className="text-[var(--sidebar-foreground)] shrink-0"
          />
        </div>
      </div>
    </aside>
  );
}
