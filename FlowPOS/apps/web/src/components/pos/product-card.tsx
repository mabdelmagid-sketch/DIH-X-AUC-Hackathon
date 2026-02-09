"use client";

import { cn, formatCurrency } from "@/lib/utils";

interface ProductCardProps {
  id: string;
  name: string;
  price: number; // in cents
  image?: string;
  onClick?: () => void;
  className?: string;
}

export function ProductCard({
  name,
  price,
  image,
  onClick,
  className,
}: ProductCardProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex w-full flex-col overflow-hidden rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] text-start transition-shadow hover:shadow-md",
        className
      )}
    >
      {/* Image */}
      <div className="relative h-[120px] w-full bg-[var(--muted)]">
        {image ? (
          <img
            src={image}
            alt={name}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-[var(--muted-foreground)]">
            <span className="material-symbols-sharp text-3xl">restaurant</span>
          </div>
        )}
      </div>

      {/* Info */}
      <div className="flex flex-col gap-1 p-3">
        <span className="font-body text-sm font-medium text-[var(--foreground)]">
          {name}
        </span>
        <span className="font-brand text-base font-semibold text-[var(--foreground)]">
          {formatCurrency(price)}
        </span>
      </div>
    </button>
  );
}
