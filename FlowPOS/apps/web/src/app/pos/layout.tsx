import { AuthGuard } from "@/components/auth/auth-guard";

export default function PosLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <AuthGuard>{children}</AuthGuard>;
}
