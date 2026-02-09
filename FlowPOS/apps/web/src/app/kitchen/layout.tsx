import { AuthGuard } from "@/components/auth/auth-guard";

export default function KitchenLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <AuthGuard>{children}</AuthGuard>;
}
