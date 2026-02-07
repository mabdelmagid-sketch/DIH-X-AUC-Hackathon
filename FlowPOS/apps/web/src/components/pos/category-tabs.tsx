"use client";

import { cn } from "@/lib/utils";

interface CategoryTabsProps {
  categories: string[];
  activeCategory: string;
  onChange: (category: string) => void;
  className?: string;
}

export function CategoryTabs({
  categories,
  activeCategory,
  onChange,
  className,
}: CategoryTabsProps) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      {categories.map((category) => {
        const isActive = category === activeCategory;
        return (
          <button
            key={category}
            onClick={() => onChange(category)}
            className={cn(
              "rounded-[var(--radius-pill)] px-4 py-1.5 font-body text-sm transition-colors",
              isActive
                ? "bg-[var(--primary)] font-medium text-white"
                : "bg-[var(--secondary)] text-[var(--muted-foreground)] hover:bg-[var(--accent)]"
            )}
          >
            {category}
          </button>
        );
      })}
    </div>
  );
}
