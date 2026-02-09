"use client";

import { cn } from "@/lib/utils";
import { Icon } from "./icon";

interface SearchBoxProps {
  placeholder?: string;
  value?: string;
  onChange?: (value: string) => void;
  className?: string;
}

export function SearchBox({
  placeholder = "Search...",
  value,
  onChange,
  className,
}: SearchBoxProps) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 h-10 rounded-[var(--radius-m)]",
        "border border-[var(--input)] bg-[var(--card)] px-3",
        className
      )}
    >
      <Icon
        name="search"
        size={20}
        className="text-[var(--muted-foreground)] shrink-0"
      />
      <input
        type="text"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        className="flex-1 bg-transparent text-sm font-body text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] outline-none min-w-0"
      />
    </div>
  );
}
