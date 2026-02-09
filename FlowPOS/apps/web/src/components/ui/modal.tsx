"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Icon } from "./icon";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  className?: string;
}

export function Modal({ open, onClose, title, children, className }: ModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (open) {
      dialog.showModal();
    } else {
      dialog.close();
    }
  }, [open]);

  return (
    <dialog
      ref={dialogRef}
      onClose={onClose}
      className={cn(
        "fixed inset-0 m-auto p-0",
        "rounded-[var(--radius-m)] border border-[var(--border)]",
        "bg-[var(--card)] text-[var(--card-foreground)] shadow-xl",
        "backdrop:bg-black/50",
        "max-h-[85vh] w-full max-w-lg overflow-hidden",
        className
      )}
    >
      {/* Header */}
      {title && (
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)]">
          <h2 className="text-lg font-brand font-semibold">{title}</h2>
          <button
            onClick={onClose}
            className="p-1 rounded-full hover:bg-[var(--accent)] cursor-pointer transition-colors"
          >
            <Icon name="close" size={20} className="text-[var(--muted-foreground)]" />
          </button>
        </div>
      )}

      {/* Content */}
      <div className="px-6 py-4 overflow-y-auto">{children}</div>
    </dialog>
  );
}
