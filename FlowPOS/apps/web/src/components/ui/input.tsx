import { forwardRef, type InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, className, id, ...props }, ref) => {
    const inputId = id || label?.toLowerCase().replace(/\s+/g, "-");

    return (
      <div className="flex flex-col gap-1.5 w-full">
        {label && (
          <label
            htmlFor={inputId}
            className="text-sm font-medium text-[var(--foreground)] font-body"
          >
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={cn(
            "h-10 w-full rounded-[var(--radius-m)] border border-[var(--input)]",
            "bg-[var(--card)] px-4 py-2.5 text-sm font-body text-[var(--foreground)]",
            "placeholder:text-[var(--muted-foreground)]",
            "focus:outline-2 focus:outline-offset-0 focus:outline-[var(--ring)]",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            error && "border-[var(--destructive)]",
            className
          )}
          {...props}
        />
        {error && (
          <p className="text-xs text-[var(--color-error-foreground)]">
            {error}
          </p>
        )}
      </div>
    );
  }
);

Input.displayName = "Input";
