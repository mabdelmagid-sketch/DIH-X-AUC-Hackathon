import { cn } from "@/lib/utils";

type StatusVariant =
  | "success"
  | "warning"
  | "error"
  | "info"
  | "secondary"
  | "violet";

interface StatusLabelProps {
  variant?: StatusVariant;
  children: React.ReactNode;
  className?: string;
}

const variantStyles: Record<StatusVariant, string> = {
  success:
    "bg-[var(--color-success)] text-[var(--color-success-foreground)]",
  warning:
    "bg-[var(--color-warning)] text-[var(--color-warning-foreground)]",
  error:
    "bg-[var(--color-error)] text-[var(--color-error-foreground)]",
  info:
    "bg-[var(--color-info)] text-[var(--color-info-foreground)]",
  secondary:
    "bg-[var(--secondary)] text-[var(--secondary-foreground)]",
  violet:
    "bg-[#EDE9FE] text-[#5B21B6]",
};

export function StatusLabel({
  variant = "secondary",
  children,
  className,
}: StatusLabelProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center px-2.5 py-0.5 rounded-full",
        "text-xs font-medium font-body whitespace-nowrap",
        variantStyles[variant],
        className
      )}
    >
      {children}
    </span>
  );
}
