import { cn, getInitials } from "@/lib/utils";

interface AvatarProps {
  name: string;
  size?: number;
  src?: string;
  className?: string;
}

export function Avatar({ name, size = 36, src, className }: AvatarProps) {
  const initials = getInitials(name);

  if (src) {
    return (
      <img
        src={src}
        alt={name}
        className={cn("rounded-full object-cover shrink-0", className)}
        style={{ width: size, height: size }}
      />
    );
  }

  return (
    <div
      className={cn(
        "inline-flex items-center justify-center rounded-full shrink-0",
        "bg-[var(--primary)] text-[var(--primary-foreground)]",
        "text-xs font-brand font-medium",
        className
      )}
      style={{ width: size, height: size }}
    >
      {initials}
    </div>
  );
}
