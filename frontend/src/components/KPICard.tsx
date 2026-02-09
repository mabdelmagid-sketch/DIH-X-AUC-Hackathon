import { cn } from "@/lib/utils";

interface KPICardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  trend?: "up" | "down" | "neutral";
  color?: "blue" | "green" | "yellow" | "red" | "gray";
}

const colorMap = {
  blue: "bg-blue-50 text-blue-700 border-blue-200",
  green: "bg-green-50 text-green-700 border-green-200",
  yellow: "bg-yellow-50 text-yellow-700 border-yellow-200",
  red: "bg-red-50 text-red-700 border-red-200",
  gray: "bg-gray-50 text-gray-700 border-gray-200",
};

export default function KPICard({
  title,
  value,
  subtitle,
  trend,
  color = "gray",
}: KPICardProps) {
  return (
    <div className={cn("rounded-xl border p-5", colorMap[color])}>
      <p className="text-xs font-medium uppercase tracking-wider opacity-70">
        {title}
      </p>
      <div className="flex items-end gap-2 mt-1">
        <p className="text-2xl font-bold">{value}</p>
        {trend && trend !== "neutral" && (
          <span className={cn("text-sm", trend === "up" ? "text-green-600" : "text-red-600")}>
            {trend === "up" ? "^" : "v"}
          </span>
        )}
      </div>
      {subtitle && <p className="text-xs mt-1 opacity-60">{subtitle}</p>}
    </div>
  );
}
