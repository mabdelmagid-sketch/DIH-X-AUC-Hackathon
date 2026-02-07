"use client";

import { useState, useRef, useEffect } from "react";
import { useTranslations } from "next-intl";
import { Icon } from "@/components/ui";
import { cn } from "@/lib/utils";

interface POSHeaderProps {
  tableName?: string;
  cashierName?: string;
  cashierInitials?: string;
  onHold?: () => void;
  onClearCart?: () => void;
  onViewHeld?: () => void;
  onBackToDashboard?: () => void;
  onSignOut?: () => void;
  heldCount?: number;
  searchValue?: string;
  onSearchChange?: (value: string) => void;
  className?: string;
}

export function POSHeader({
  tableName,
  cashierName = "Cashier",
  cashierInitials = "C",
  onHold,
  onClearCart,
  onViewHeld,
  onBackToDashboard,
  onSignOut,
  heldCount = 0,
  searchValue = "",
  onSearchChange,
  className,
}: POSHeaderProps) {
  const t = useTranslations("pos");
  const tc = useTranslations("common");
  const tn = useTranslations("nav");
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close menu on outside click
  useEffect(() => {
    if (!menuOpen) return;
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuOpen]);

  return (
    <header
      className={cn(
        "flex h-16 items-center justify-between border-b border-[var(--border)] bg-[var(--card)] px-5",
        className
      )}
    >
      {/* Left: Logo + Search */}
      <div className="flex items-center gap-4">
        <span className="font-brand text-lg font-bold text-[var(--primary)]">
          {tc("flowPos")}
        </span>
        <div className="relative w-[280px]">
          <Icon
            name="search"
            size={18}
            className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]"
          />
          <input
            type="text"
            placeholder={t("searchProducts")}
            value={searchValue}
            onChange={(e) => onSearchChange?.(e.target.value)}
            className="h-10 w-full rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] ps-10 pe-4 font-body text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--ring)]"
          />
        </div>
      </div>

      {/* Right: Table + Cashier + Actions */}
      <div className="flex items-center gap-3">
        {tableName && (
          <span className="rounded-[var(--radius-pill)] border border-[var(--border)] px-3 py-1 font-body text-xs text-[var(--muted-foreground)]">
            {tableName}
          </span>
        )}
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[var(--primary)] text-xs font-medium text-white">
          {cashierInitials}
        </div>
        <span className="font-body text-sm text-[var(--foreground)]">
          {cashierName}
        </span>
        <button
          onClick={onHold}
          className="relative flex items-center gap-2 rounded-[var(--radius-pill)] px-4 py-2 font-brand text-sm text-[var(--foreground)] hover:bg-[var(--accent)] transition-colors"
        >
          <Icon name="pause_circle" size={18} />
          {t("hold")}
          {heldCount > 0 && (
            <span className="absolute -top-1 -end-1 flex h-5 w-5 items-center justify-center rounded-full bg-[var(--primary)] text-[10px] font-bold text-white">
              {heldCount}
            </span>
          )}
        </button>

        {/* Three-dot menu */}
        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setMenuOpen((v) => !v)}
            className="flex h-10 w-10 items-center justify-center rounded-[var(--radius-pill)] border border-[var(--border)] text-[var(--foreground)] hover:bg-[var(--accent)] transition-colors"
          >
            <Icon name="more_vert" size={20} />
          </button>

          {menuOpen && (
            <div className="absolute end-0 top-12 z-50 w-52 rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] py-1 shadow-lg">
              {onViewHeld && (
                <button
                  onClick={() => { setMenuOpen(false); onViewHeld(); }}
                  className="flex w-full items-center gap-3 px-4 py-2.5 font-body text-sm text-[var(--foreground)] hover:bg-[var(--accent)] transition-colors"
                >
                  <Icon name="inventory_2" size={18} className="text-[var(--muted-foreground)]" />
                  {t("heldOrders")}
                  {heldCount > 0 && (
                    <span className="ms-auto rounded-[var(--radius-pill)] bg-[var(--primary)] px-2 py-0.5 text-[10px] font-bold text-white">
                      {heldCount}
                    </span>
                  )}
                </button>
              )}
              {onClearCart && (
                <button
                  onClick={() => { setMenuOpen(false); onClearCart(); }}
                  className="flex w-full items-center gap-3 px-4 py-2.5 font-body text-sm text-[var(--foreground)] hover:bg-[var(--accent)] transition-colors"
                >
                  <Icon name="delete_sweep" size={18} className="text-[var(--muted-foreground)]" />
                  {t("clearCart")}
                </button>
              )}
              <div className="my-1 border-t border-[var(--border)]" />
              {onBackToDashboard && (
                <button
                  onClick={() => { setMenuOpen(false); onBackToDashboard(); }}
                  className="flex w-full items-center gap-3 px-4 py-2.5 font-body text-sm text-[var(--foreground)] hover:bg-[var(--accent)] transition-colors"
                >
                  <Icon name="dashboard" size={18} className="text-[var(--muted-foreground)]" />
                  {tn("dashboard")}
                </button>
              )}
              {onSignOut && (
                <button
                  onClick={() => { setMenuOpen(false); onSignOut(); }}
                  className="flex w-full items-center gap-3 px-4 py-2.5 font-body text-sm text-[var(--destructive)] hover:bg-[var(--accent)] transition-colors"
                >
                  <Icon name="logout" size={18} />
                  {tc("signOut")}
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
