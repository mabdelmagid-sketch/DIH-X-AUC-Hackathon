"use client";

import { formatCurrency } from "@/lib/utils";

interface CartItemProps {
  name: string;
  quantity: number;
  price: number; // unit price in cents
  onIncrement?: () => void;
  onDecrement?: () => void;
  onRemove?: () => void;
}

export function CartItem({ name, quantity, price, onIncrement, onDecrement, onRemove }: CartItemProps) {
  return (
    <div className="flex items-center justify-between border-b border-[var(--border)] py-3">
      <div className="flex flex-1 flex-col gap-0.5 min-w-0">
        <span className="font-body text-sm font-medium text-[var(--foreground)] truncate">
          {name}
        </span>
        <span className="font-brand text-sm text-[var(--foreground)]">
          {formatCurrency(price * quantity)}
        </span>
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        {/* Decrement / Remove */}
        <button
          onClick={quantity <= 1 ? onRemove : onDecrement}
          className="flex h-7 w-7 items-center justify-center rounded-full bg-[var(--secondary)] text-[var(--foreground)] hover:bg-[var(--border)] active:scale-95 transition-all cursor-pointer"
        >
          <span className="material-symbols-sharp text-base">
            {quantity <= 1 ? "delete" : "remove"}
          </span>
        </button>

        {/* Quantity */}
        <span className="w-6 text-center font-brand text-sm font-medium text-[var(--foreground)]">
          {quantity}
        </span>

        {/* Increment */}
        <button
          onClick={onIncrement}
          className="flex h-7 w-7 items-center justify-center rounded-full bg-[var(--secondary)] text-[var(--foreground)] hover:bg-[var(--border)] active:scale-95 transition-all cursor-pointer"
        >
          <span className="material-symbols-sharp text-base">add</span>
        </button>
      </div>
    </div>
  );
}
