"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Button, Input } from "@/components/ui";
import { useAuthStore } from "@/store/auth-store";
import { getSupabaseClient } from "@/lib/supabase";

export default function LoginPage() {
  const router = useRouter();
  const { loginWithSupabase } = useAuthStore();
  const t = useTranslations("auth");
  const tc = useTranslations("common");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [magicLinkSent, setMagicLinkSent] = useState(false);

  async function handleSignIn(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    const result = await loginWithSupabase(email, password);

    if (result.error) {
      setError(result.error.message || t("invalidCredentials"));
      setIsLoading(false);
      return;
    }

    // Read fresh state directly from store after login + sync completed
    const state = useAuthStore.getState();
    if (state.isPlatformAdmin) {
      router.replace("/admin/system");
    } else {
      router.replace("/dashboard");
    }
  }

  async function handleMagicLink() {
    if (!email) {
      setError(t("emailRequired"));
      return;
    }

    setError(null);
    setIsLoading(true);

    try {
      const supabase = getSupabaseClient();
      const { error: otpError } = await supabase.auth.signInWithOtp({
        email,
        options: {
          emailRedirectTo: `${window.location.origin}/auth/callback`,
        },
      });

      if (otpError) {
        setError(otpError.message);
      } else {
        setMagicLinkSent(true);
      }
    } catch {
      setError(t("magicLinkFailed"));
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="flex h-full">
      {/* Brand Panel - hidden on tablet/phone */}
      <div className="hidden lg:flex flex-1 items-center justify-center bg-[var(--primary)] p-12">
        <div className="text-center">
          <h1 className="text-4xl font-brand font-bold text-white">
            {tc("flowPos")}
          </h1>
          <p className="mt-4 text-lg font-body text-white/90 max-w-[340px]">
            {t("tagline")}
          </p>
        </div>
      </div>

      {/* Form Panel */}
      <div className="flex flex-1 lg:flex-none lg:w-[520px] items-center justify-center bg-[var(--card)] p-12">
        <div className="w-full max-w-[380px]">
          {/* Mobile logo */}
          <div className="lg:hidden text-center mb-8">
            <h1 className="text-2xl font-brand font-bold text-[var(--primary)]">
              {tc("flowPos")}
            </h1>
          </div>

          {/* Header */}
          <div className="mb-8">
            <h2 className="text-xl font-brand font-bold text-[var(--foreground)]">
              {t("welcomeBack")}
            </h2>
            <p className="mt-2 text-sm font-body text-[var(--muted-foreground)]">
              {t("signInToAccount")}
            </p>
          </div>

          {/* Magic Link Sent Confirmation */}
          {magicLinkSent ? (
            <div className="flex flex-col items-center gap-4 rounded-[var(--radius-m)] border border-[var(--color-success)] bg-[var(--color-success)] p-6 text-center">
              <span className="material-symbols-sharp text-[var(--color-success-foreground)]" style={{ fontSize: 40 }}>
                mark_email_read
              </span>
              <h3 className="font-brand text-base font-semibold text-[var(--color-success-foreground)]">
                {t("checkYourEmail")}
              </h3>
              <p className="text-sm font-body text-[var(--color-success-foreground)]">
                {t("magicLinkSent")} <strong>{email}</strong>. {t("magicLinkInstruction")}
              </p>
              <Button
                type="button"
                variant="outline"
                onClick={() => setMagicLinkSent(false)}
              >
                {t("backToLogin")}
              </Button>
            </div>
          ) : (
            <>
              {/* Error Message */}
              {error && (
                <div className="mb-4 rounded-[var(--radius-m)] border border-[var(--color-error)] bg-[var(--color-error)] px-4 py-3">
                  <p className="text-sm font-body text-[var(--color-error-foreground)]">
                    {error}
                  </p>
                </div>
              )}

              {/* Form */}
              <form onSubmit={handleSignIn} className="flex flex-col gap-4">
                <Input
                  label={tc("email")}
                  type="email"
                  placeholder={t("emailPlaceholder")}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
                <Input
                  label={t("password")}
                  type="password"
                  placeholder={t("passwordPlaceholder")}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />

                <div className="flex flex-col gap-3 mt-2">
                  <Button type="submit" variant="primary" disabled={isLoading}>
                    {isLoading ? t("signingIn") : t("signIn")}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={handleMagicLink}
                    disabled={isLoading}
                  >
                    {t("signInMagicLink")}
                  </Button>
                </div>
              </form>

              {/* PIN Login Link */}
              <p className="mt-6 text-center text-sm font-body text-[var(--foreground)]">
                <Link
                  href="/pin"
                  className="hover:underline"
                >
                  {t("signInWithPin")}
                </Link>
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
