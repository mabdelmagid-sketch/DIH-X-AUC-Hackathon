"use client";

import { useRouter } from "next/navigation";
import { useLocale } from "next-intl";
import { Icon } from "@/components/ui";

export function LanguageSwitcher() {
  const locale = useLocale();
  const router = useRouter();

  function toggleLocale() {
    const next = locale === "en" ? "ar" : "en";
    document.cookie = `locale=${next};path=/;max-age=31536000`;
    router.refresh();
  }

  return (
    <button
      onClick={toggleLocale}
      className="flex items-center gap-2 rounded-[var(--radius-pill)] px-3 py-1.5 font-body text-xs text-[var(--sidebar-foreground)] hover:bg-[var(--sidebar-accent)] hover:text-[var(--sidebar-accent-foreground)] transition-colors"
    >
      <Icon name="translate" size={16} />
      {locale === "en" ? "العربية" : "English"}
    </button>
  );
}
