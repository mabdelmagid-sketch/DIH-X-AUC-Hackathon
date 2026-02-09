import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";
import { Icon } from "./icon";

type ButtonVariant =
  | "primary"
  | "secondary"
  | "outline"
  | "destructive"
  | "ghost";

type ButtonSize = "default" | "large" | "icon";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: string;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary:
    "bg-[var(--primary)] text-[var(--primary-foreground)] hover:opacity-90",
  secondary:
    "bg-[var(--secondary)] text-[var(--secondary-foreground)] hover:opacity-90",
  outline:
    "bg-[var(--card)] text-[var(--foreground)] border border-[var(--border)] shadow-sm hover:bg-[var(--accent)]",
  destructive:
    "bg-[#FF5C33] text-white hover:opacity-90",
  ghost:
    "text-[var(--muted-foreground)] hover:bg-[var(--accent)] hover:text-[var(--foreground)]",
};

const sizeStyles: Record<ButtonSize, string> = {
  default: "h-10 px-4 py-2.5 text-sm",
  large: "h-12 px-6 py-3 text-sm",
  icon: "h-10 w-10 p-2.5",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = "primary",
      size = "default",
      icon,
      children,
      className,
      disabled,
      ...props
    },
    ref
  ) => {
    return (
      <button
        ref={ref}
        disabled={disabled}
        className={cn(
          "inline-flex items-center justify-center gap-1.5 rounded-full font-brand font-medium",
          "transition-all duration-150 cursor-pointer",
          "disabled:opacity-50 disabled:cursor-not-allowed",
          "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--ring)]",
          variantStyles[variant],
          sizeStyles[size],
          className
        )}
        {...props}
      >
        {icon && (
          <Icon
            name={icon}
            size={size === "large" ? 24 : 20}
            className={
              size === "icon"
                ? ""
                : variant === "ghost"
                  ? "text-[var(--muted-foreground)]"
                  : ""
            }
          />
        )}
        {size !== "icon" && children}
      </button>
    );
  }
);

Button.displayName = "Button";
