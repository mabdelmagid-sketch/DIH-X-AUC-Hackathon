"use client";

import { useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import { Icon, LanguageSwitcher } from "@/components/ui";
import { useAuthStore } from "@/store/auth-store";

/* ------------------------------------------------------------------ */
/*  Navigation Configuration                                           */
/* ------------------------------------------------------------------ */

interface NavItem {
  labelKey: string;
  icon: string;
  href: string;
}

interface NavSection {
  titleKey: string;
  items: NavItem[];
}

const navigation: NavSection[] = [
  {
    titleKey: "main",
    items: [
      { labelKey: "posTerminal", icon: "point_of_sale", href: "/pos" },
      { labelKey: "dashboard", icon: "dashboard", href: "/dashboard" },
      { labelKey: "orders", icon: "receipt_long", href: "/dashboard/orders" },
      { labelKey: "products", icon: "inventory_2", href: "/dashboard/products" },
      { labelKey: "customers", icon: "people", href: "/dashboard/customers" },
      { labelKey: "employees", icon: "badge", href: "/dashboard/employees" },
      { labelKey: "inventory", icon: "warehouse", href: "/dashboard/inventory" },
      { labelKey: "tables", icon: "table_restaurant", href: "/dashboard/tables" },
      { labelKey: "loyalty", icon: "loyalty", href: "/dashboard/loyalty" },
      { labelKey: "coupons", icon: "local_offer", href: "/dashboard/coupons" },
      { labelKey: "recipes", icon: "menu_book", href: "/dashboard/recipes" },
      { labelKey: "ingredients", icon: "science", href: "/dashboard/ingredients" },
      { labelKey: "suppliers", icon: "local_shipping", href: "/dashboard/suppliers" },
    ],
  },
  {
    titleKey: "ai",
    items: [
      { labelKey: "forecast", icon: "trending_up", href: "/dashboard/forecast" },
      { labelKey: "insights", icon: "lightbulb", href: "/dashboard/insights" },
      { labelKey: "simulator", icon: "science", href: "/dashboard/simulator" },
    ],
  },
  {
    titleKey: "analytics",
    items: [
      { labelKey: "reports", icon: "bar_chart", href: "/dashboard/reports" },
      { labelKey: "settings", icon: "settings", href: "/dashboard/settings" },
    ],
  },
];

/* ------------------------------------------------------------------ */
/*  Nav Item                                                           */
/* ------------------------------------------------------------------ */

function SidebarNavItem({
  item,
  isActive,
  label,
}: {
  item: NavItem;
  isActive: boolean;
  label: string;
}) {
  return (
    <Link
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
      <span>{label}</span>
    </Link>
  );
}

/* ------------------------------------------------------------------ */
/*  Sidebar                                                            */
/* ------------------------------------------------------------------ */

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, organization, logout } = useAuthStore();
  const [showMenu, setShowMenu] = useState(false);
  const t = useTranslations("nav");
  const tc = useTranslations("common");

  const userName = user?.name ?? "User";
  const userEmail = user?.email ?? organization?.name ?? "";

  function isActive(href: string) {
    if (href === "/dashboard") return pathname === "/dashboard";
    if (href === "/pos") return pathname === "/pos";
    return pathname.startsWith(href);
  }

  async function handleLogout() {
    await logout();
    router.replace("/login");
  }

  return (
    <aside className="flex flex-col w-[280px] h-full bg-[var(--sidebar)] border-e border-[var(--sidebar-border)] shrink-0">
      {/* Logo */}
      <div className="flex items-center h-[88px] px-8">
        <span className="text-lg font-brand font-bold text-[var(--primary)]">
          {tc("flowPos")}
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-4">
        {navigation.map((section) => (
          <div key={section.titleKey} className="mb-1">
            <p className="px-4 py-1.5 text-sm font-brand text-[var(--sidebar-foreground)]">
              {t(section.titleKey)}
            </p>
            {section.items.map((item) => (
              <SidebarNavItem
                key={item.href}
                item={item}
                isActive={isActive(item.href)}
                label={t(item.labelKey)}
              />
            ))}
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="relative px-8 py-6 border-t border-[var(--sidebar-border)]">
        <div className="flex items-center justify-between mb-3">
          <LanguageSwitcher />
        </div>
        <button
          onClick={() => setShowMenu((prev) => !prev)}
          className="flex w-full items-center gap-2 cursor-pointer"
        >
          <div className="flex-1 min-w-0 text-start">
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
            className={cn(
              "text-[var(--sidebar-foreground)] shrink-0 transition-transform",
              showMenu && "rotate-180"
            )}
          />
        </button>

        {/* Dropdown menu */}
        {showMenu && (
          <div className="absolute bottom-full start-4 end-4 mb-2 rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] shadow-lg overflow-hidden">
            <button
              onClick={handleLogout}
              className="flex w-full items-center gap-3 px-4 py-3 text-sm font-body text-[var(--destructive)] hover:bg-[var(--accent)] transition-colors cursor-pointer"
            >
              <Icon name="logout" size={20} className="text-[var(--destructive)]" />
              {tc("signOut")}
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
