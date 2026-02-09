"use client";

import { useTranslations } from "next-intl";
import { Icon } from "@/components/ui";
import { formatCurrency } from "@/lib/utils";
import type { HeldOrder } from "@/store/held-orders-store";

interface HeldOrdersDrawerProps {
  open: boolean;
  onClose: () => void;
  orders: HeldOrder[];
  onRecall: (id: string) => void;
  onRemove: (id: string) => void;
}

export function HeldOrdersDrawer({
  open,
  onClose,
  orders,
  onRecall,
  onRemove,
}: HeldOrdersDrawerProps) {
  const t = useTranslations("pos");

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/40"
        onClick={onClose}
      />

      {/* Drawer */}
      <div className="fixed inset-y-0 end-0 z-50 flex w-[380px] flex-col bg-[var(--card)] shadow-xl">
        {/* Header */}
        <div className="flex h-16 items-center justify-between border-b border-[var(--border)] px-5">
          <h2 className="font-brand text-lg font-semibold text-[var(--foreground)]">
            {t("heldOrders")}
          </h2>
          <button
            onClick={onClose}
            className="flex h-9 w-9 items-center justify-center rounded-full hover:bg-[var(--accent)] transition-colors"
          >
            <Icon name="close" size={20} className="text-[var(--foreground)]" />
          </button>
        </div>

        {/* Orders list */}
        <div className="flex-1 overflow-y-auto p-4">
          {orders.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-[var(--muted-foreground)]">
              <Icon name="inventory_2" size={40} />
              <span className="font-body text-sm">{t("noHeldOrders")}</span>
              <span className="font-body text-xs">{t("holdOrderHint")}</span>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {orders.map((order) => {
                const total = order.items.reduce(
                  (sum, item) => sum + item.price * item.quantity,
                  0
                );
                const itemCount = order.items.reduce(
                  (sum, item) => sum + item.quantity,
                  0
                );
                const heldAt = new Date(order.heldAt);
                const timeAgo = getTimeAgo(heldAt);

                return (
                  <div
                    key={order.id}
                    className="flex flex-col gap-3 rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--background)] p-4"
                  >
                    {/* Order info */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Icon name="receipt_long" size={16} className="text-[var(--muted-foreground)]" />
                        <span className="font-body text-sm font-medium text-[var(--foreground)]">
                          {itemCount} item{itemCount !== 1 ? "s" : ""}
                        </span>
                      </div>
                      <span className="font-body text-xs text-[var(--muted-foreground)]">
                        {timeAgo}
                      </span>
                    </div>

                    {/* Items preview */}
                    <div className="flex flex-col gap-1">
                      {order.items.slice(0, 3).map((item) => (
                        <div
                          key={item.id}
                          className="flex items-center justify-between font-body text-xs text-[var(--muted-foreground)]"
                        >
                          <span>
                            {item.quantity}x {item.name}
                          </span>
                          <span>{formatCurrency(item.price * item.quantity)}</span>
                        </div>
                      ))}
                      {order.items.length > 3 && (
                        <span className="font-body text-xs text-[var(--muted-foreground)]">
                          +{order.items.length - 3} more...
                        </span>
                      )}
                    </div>

                    {/* Total + actions */}
                    <div className="flex items-center justify-between border-t border-[var(--border)] pt-3">
                      <span className="font-brand text-sm font-semibold text-[var(--foreground)]">
                        {formatCurrency(total)}
                      </span>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => onRemove(order.id)}
                          className="flex h-8 items-center gap-1 rounded-[var(--radius-pill)] px-3 font-body text-xs text-[var(--destructive)] hover:bg-[var(--accent)] transition-colors"
                        >
                          <Icon name="delete" size={14} />
                          {t("discard")}
                        </button>
                        <button
                          onClick={() => onRecall(order.id)}
                          className="flex h-8 items-center gap-1 rounded-[var(--radius-pill)] bg-[var(--primary)] px-3 font-body text-xs font-medium text-white hover:bg-[var(--primary)]/90 transition-colors"
                        >
                          <Icon name="replay" size={14} />
                          {t("recall")}
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function getTimeAgo(date: Date): string {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return "Just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}
