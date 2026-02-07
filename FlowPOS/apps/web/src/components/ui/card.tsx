import { cn } from "@/lib/utils";

interface CardProps {
  children: React.ReactNode;
  className?: string;
}

export function Card({ children, className }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-[var(--radius-m)] border border-[var(--border)]",
        "bg-[var(--card)] text-[var(--card-foreground)]",
        className
      )}
    >
      {children}
    </div>
  );
}

export function CardHeader({ children, className }: CardProps) {
  return (
    <div
      className={cn(
        "flex items-center justify-between px-5 py-4",
        "border-b border-[var(--border)]",
        className
      )}
    >
      {children}
    </div>
  );
}

export function CardContent({ children, className }: CardProps) {
  return (
    <div className={cn("px-5 py-4", className)}>
      {children}
    </div>
  );
}

export function CardActions({ children, className }: CardProps) {
  return (
    <div
      className={cn(
        "flex items-center justify-end gap-2 px-5 py-4",
        "border-t border-[var(--border)]",
        className
      )}
    >
      {children}
    </div>
  );
}
