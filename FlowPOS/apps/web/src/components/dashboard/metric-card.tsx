import { cn } from "@/lib/utils";

interface MetricCardProps {
  label: string;
  value: string;
  change?: string;
  changeType?: "positive" | "negative" | "neutral";
}

export function MetricCard({
  label,
  value,
  change,
  changeType = "positive",
}: MetricCardProps) {
  return (
    <div className="flex w-full flex-col gap-1 rounded-[var(--radius-m)] border border-[var(--border)] bg-[var(--card)] px-6 py-5">
      <span className="font-body text-[13px] text-[var(--foreground)]">
        {label}
      </span>
      <div className="flex items-center gap-2">
        <span className="font-brand text-[28px] font-bold text-[var(--foreground)]">
          {value}
        </span>
        {change && (
          <span
            className={cn(
              "rounded-[var(--radius-pill)] border border-[var(--border)] bg-[var(--card)] px-2 py-0.5 font-body text-xs font-medium",
              changeType === "positive" && "text-[var(--color-success-foreground)]",
              changeType === "negative" && "text-[var(--color-warning-foreground)]",
              changeType === "neutral" && "text-[var(--muted-foreground)]"
            )}
          >
            {change}
          </span>
        )}
      </div>
    </div>
  );
}
