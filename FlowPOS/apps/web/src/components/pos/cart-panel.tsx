"use client";

import { useState, useRef, useEffect } from "react";
import { useTranslations } from "next-intl";
import { useCartStore, type CartCustomer } from "@/store/cart-store";
import { CartItem } from "./cart-item";
import { formatCurrency } from "@/lib/utils";
import { Icon } from "@/components/ui";
import { trpc } from "@/lib/trpc";

/* ─── Customer Picker (inline search dropdown) ─────────── */

function CustomerPicker() {
  const t = useTranslations("pos");
  const customer = useCartStore((s) => s.customer);
  const setCustomer = useCartStore((s) => s.setCustomer);
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const { data } = trpc.customers.list.useQuery(
    { search: search || undefined, limit: 6 },
    { enabled: open }
  );

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Focus input when opened
  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  // Customer is attached — show chip
  if (customer) {
    return (
      <div className="flex items-center justify-between rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--background)] px-3 py-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--primary)] text-[10px] font-bold text-white">
            {customer.name.charAt(0).toUpperCase()}
          </div>
          <div className="flex flex-col min-w-0">
            <span className="truncate font-body text-sm font-medium text-[var(--foreground)]">
              {customer.name}
            </span>
            {customer.loyaltyPoints != null && customer.loyaltyPoints > 0 && (
              <span className="font-body text-[10px] text-[var(--muted-foreground)]">
                {customer.loyaltyPoints} {t("pts")}
              </span>
            )}
          </div>
        </div>
        <button
          onClick={() => setCustomer(null)}
          className="rounded-full p-1 text-[var(--muted-foreground)] hover:bg-[var(--accent)] hover:text-[var(--foreground)] transition-colors"
        >
          <Icon name="close" size={14} />
        </button>
      </div>
    );
  }

  // No customer — show "Add customer" button / search
  return (
    <div ref={containerRef} className="relative">
      {open ? (
        <div className="flex flex-col">
          <div className="relative">
            <Icon
              name="search"
              size={14}
              className="pointer-events-none absolute start-2.5 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]"
            />
            <input
              ref={inputRef}
              type="text"
              placeholder={t("searchCustomers")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") { setOpen(false); setSearch(""); }
              }}
              className="h-9 w-full rounded-[var(--radius-m)] border border-[var(--input)] bg-[var(--background)] ps-8 pe-3 font-body text-xs text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--ring)]"
            />
          </div>

          {/* Dropdown results */}
          <div className="absolute top-10 z-10 w-full rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] shadow-lg">
            {!data ? (
              <div className="flex items-center justify-center py-4">
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
              </div>
            ) : data.customers.length === 0 ? (
              <div className="px-3 py-4 text-center font-body text-xs text-[var(--muted-foreground)]">
                {search ? t("noCustomersFound") : t("noCustomersYet")}
              </div>
            ) : (
              <div className="max-h-48 overflow-y-auto py-1">
                {data.customers.map((c: { id: string; name: string; phone: string | null; loyalty_points: number | null }) => (
                  <button
                    key={c.id}
                    onClick={() => {
                      setCustomer({
                        id: c.id,
                        name: c.name,
                        phone: c.phone,
                        loyaltyPoints: c.loyalty_points,
                      });
                      setOpen(false);
                      setSearch("");
                    }}
                    className="flex w-full items-center gap-2 px-3 py-2 text-start transition-colors hover:bg-[var(--accent)]"
                  >
                    <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--secondary)] text-[10px] font-bold text-[var(--foreground)]">
                      {c.name.charAt(0).toUpperCase()}
                    </div>
                    <div className="flex flex-col min-w-0">
                      <span className="truncate font-body text-xs font-medium text-[var(--foreground)]">{c.name}</span>
                      {c.phone && (
                        <span className="font-body text-[10px] text-[var(--muted-foreground)]">{c.phone}</span>
                      )}
                    </div>
                    {c.loyalty_points != null && c.loyalty_points > 0 && (
                      <span className="ms-auto shrink-0 rounded-[var(--radius-pill)] bg-[var(--color-success)] px-1.5 py-0.5 font-body text-[10px] font-medium text-[var(--color-success-foreground)]">
                        {c.loyalty_points} {t("pts")}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      ) : (
        <button
          onClick={() => setOpen(true)}
          className="flex w-full items-center gap-2 rounded-[var(--radius-m)] border border-dashed border-[var(--border)] px-3 py-2 font-body text-xs text-[var(--muted-foreground)] transition-colors hover:border-[var(--primary)] hover:text-[var(--primary)]"
        >
          <Icon name="person_add" size={14} />
          {t("addCustomer")}
        </button>
      )}
    </div>
  );
}

/* ─── Cart Panel (desktop sidebar) ─────────────────────── */

export function CartPanel() {
  const t = useTranslations("pos");
  const tc = useTranslations("common");
  const items = useCartStore((s) => s.items);
  const removeItem = useCartStore((s) => s.removeItem);
  const updateQuantity = useCartStore((s) => s.updateQuantity);
  const subtotal = useCartStore((s) => s.subtotal);
  const tax = useCartStore((s) => s.tax);
  const total = useCartStore((s) => s.total);
  const itemCount = useCartStore((s) => s.itemCount);

  return (
    <div className="flex h-full w-[360px] flex-col border-s border-[var(--border)] bg-[var(--card)]">
      {/* Cart Header */}
      <div className="flex h-[52px] items-center justify-between border-b border-[var(--border)] px-5">
        <span className="font-brand text-base font-semibold text-[var(--foreground)]">
          {t("currentOrder")}
        </span>
        <span className="rounded-[var(--radius-pill)] border border-[var(--border)] px-3 py-1 font-body text-xs text-[var(--muted-foreground)]">
          {itemCount()} {tc("items")}
        </span>
      </div>

      {/* Cart Items */}
      <div className="flex-1 overflow-y-auto px-5 py-3">
        {items.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-[var(--muted-foreground)]">
            <Icon name="shopping_cart" size={32} />
            <span className="font-body text-sm">{t("noItemsYet")}</span>
          </div>
        ) : (
          items.map((item) => (
            <CartItem
              key={item.id}
              name={item.name}
              quantity={item.quantity}
              price={item.price}
              onIncrement={() => updateQuantity(item.id, item.quantity + 1)}
              onDecrement={() => updateQuantity(item.id, item.quantity - 1)}
              onRemove={() => removeItem(item.id)}
            />
          ))
        )}
      </div>

      {/* Cart Footer */}
      {items.length > 0 && (
        <div className="flex flex-col gap-3 border-t border-[var(--border)] p-5">
          {/* Customer picker */}
          <CustomerPicker />

          <div className="flex items-center justify-between">
            <span className="font-body text-sm text-[var(--foreground)]">
              {t("subtotal")}
            </span>
            <span className="font-body text-sm text-[var(--foreground)]">
              {formatCurrency(subtotal())}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="font-body text-sm text-[var(--foreground)]">
              {t("tax")}
            </span>
            <span className="font-body text-sm text-[var(--foreground)]">
              {formatCurrency(tax())}
            </span>
          </div>
          <div className="flex items-center justify-between border-t border-[var(--border)] pt-2">
            <span className="font-brand text-lg font-semibold text-[var(--foreground)]">
              {t("total")}
            </span>
            <span className="font-brand text-lg font-semibold text-[var(--foreground)]">
              {formatCurrency(total())}
            </span>
          </div>
          <button className="flex h-12 w-full items-center justify-center rounded-[var(--radius-pill)] bg-[var(--primary)] font-brand text-base font-semibold text-white transition-colors hover:bg-[var(--primary)]/90">
            {t("pay")} {formatCurrency(total())}
          </button>
        </div>
      )}
    </div>
  );
}

/** Compact bottom bar for tablet/mobile */
export function CartBottomBar() {
  const t = useTranslations("pos");
  const tc = useTranslations("common");
  const itemCount = useCartStore((s) => s.itemCount);
  const total = useCartStore((s) => s.total);

  if (itemCount() === 0) return null;

  return (
    <div className="flex h-16 items-center justify-between border-t border-[var(--border)] bg-[var(--card)] px-5 lg:hidden">
      <div className="flex items-center gap-2 text-[var(--muted-foreground)]">
        <Icon name="shopping_cart" size={20} />
        <span className="font-body text-sm">{itemCount()} {tc("items")}</span>
      </div>
      <span className="font-brand text-base font-semibold text-[var(--foreground)]">
        {t("total")}: {formatCurrency(total())}
      </span>
      <button className="rounded-[var(--radius-pill)] bg-[var(--primary)] px-6 py-2 font-brand text-sm font-semibold text-white transition-colors hover:bg-[var(--primary)]/90">
        {t("pay")} {formatCurrency(total())}
      </button>
    </div>
  );
}
