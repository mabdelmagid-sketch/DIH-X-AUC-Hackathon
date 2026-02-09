"use client";

import { cn } from "@/lib/utils";

export type OrderStatus = "new" | "in_progress" | "ready";

export interface KDSOrderItem {
  name: string;
  quantity: number;
  modifier?: string;
}

export interface KDSOrder {
  id: string;
  orderNumber: string;
  status: OrderStatus;
  items: KDSOrderItem[];
  table?: string;
  type?: string; // "Dine In", "Takeaway", etc.
  elapsedMinutes: number;
}

interface OrderCardProps {
  order: KDSOrder;
  onBump?: (id: string) => void;
  onStart?: (id: string) => void;
}

function getTimerColor(minutes: number): string {
  if (minutes >= 5) return "bg-[var(--destructive)]";
  if (minutes >= 2) return "bg-amber-400";
  return "bg-[var(--primary)]";
}

function formatTime(minutes: number): string {
  const m = Math.floor(minutes);
  const s = Math.round((minutes - m) * 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function OrderCard({ order, onBump, onStart }: OrderCardProps) {
  return (
    <div className="flex flex-col overflow-hidden rounded-[var(--radius-m)] border-2 border-[var(--border)] bg-[var(--card)]">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3">
        <span className="font-brand text-base font-bold text-[var(--foreground)]">
          #{order.orderNumber}
        </span>
        <div className="flex items-center gap-1.5">
          <span
            className={cn(
              "h-2.5 w-2.5 rounded-full",
              getTimerColor(order.elapsedMinutes)
            )}
          />
          <span className="font-brand text-sm font-semibold text-[var(--foreground)]">
            {formatTime(order.elapsedMinutes)}
          </span>
        </div>
      </div>

      {/* Items */}
      <div className="flex flex-col gap-1.5 px-4 py-3">
        {order.items.map((item, idx) => (
          <div key={idx} className="flex flex-col">
            <span
              className={cn(
                "font-body text-sm text-[var(--foreground)]",
                idx === 0 ? "font-medium" : "font-normal"
              )}
            >
              {item.quantity}x {item.name}
            </span>
            {item.modifier && (
              <span className="font-body text-xs font-semibold text-[var(--foreground)]">
                {item.modifier}
              </span>
            )}
          </div>
        ))}
        {order.type && (
          <span className="mt-1 font-body text-xs font-semibold text-[var(--muted-foreground)]">
            {order.type}
          </span>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between border-t border-[var(--border)] px-4 py-3">
        <span className="font-body text-[13px] text-[var(--foreground)]">
          {order.table || ""}
        </span>
        {order.status === "in_progress" ? (
          <button
            onClick={() => onBump?.(order.id)}
            className="rounded-[var(--radius-pill)] bg-[var(--primary)] px-5 py-2 font-brand text-sm font-semibold text-white transition-colors hover:bg-[var(--primary)]/90"
          >
            BUMP
          </button>
        ) : order.status === "new" ? (
          <button
            onClick={() => onStart?.(order.id)}
            className="rounded-[var(--radius-pill)] bg-[var(--secondary)] px-5 py-2 font-brand text-sm font-semibold text-[var(--secondary-foreground)] transition-colors hover:bg-[var(--accent)]"
          >
            START
          </button>
        ) : null}
      </div>
    </div>
  );
}
