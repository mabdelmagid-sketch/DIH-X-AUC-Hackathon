"use client";

import { forwardRef, type SelectHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps
  extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "onChange"> {
  label?: string;
  options: SelectOption[];
  onChange?: (value: string) => void;
  error?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, options, onChange, error, className, id, value, ...props }, ref) => {
    const selectId = id || label?.toLowerCase().replace(/\s+/g, "-");

    return (
      <div className="flex flex-col gap-1.5 w-full">
        {label && (
          <label
            htmlFor={selectId}
            className="text-sm font-medium text-[var(--foreground)] font-body"
          >
            {label}
          </label>
        )}
        <select
          ref={ref}
          id={selectId}
          value={value}
          onChange={(e) => onChange?.(e.target.value)}
          className={cn(
            "h-10 w-full rounded-[var(--radius-m)] border border-[var(--input)]",
            "bg-[var(--card)] px-4 py-2.5 text-sm font-body text-[var(--foreground)]",
            "appearance-none cursor-pointer",
            "focus:outline-2 focus:outline-offset-0 focus:outline-[var(--ring)]",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            error && "border-[var(--destructive)]",
            className
          )}
          {...props}
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        {error && (
          <p className="text-xs text-[var(--color-error-foreground)]">
            {error}
          </p>
        )}
      </div>
    );
  }
);

Select.displayName = "Select";
