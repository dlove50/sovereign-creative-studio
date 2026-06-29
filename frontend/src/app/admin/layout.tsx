import { RequireAdmin } from "@/components/require-admin";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <RequireAdmin>{children}</RequireAdmin>;
}
