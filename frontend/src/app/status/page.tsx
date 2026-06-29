import { PageHeader } from "@/components/page-header";
import { StatusView } from "@/components/status-view";
import { RequireAdmin } from "@/components/require-admin";

export default function StatusPage() {
  return (
    <RequireAdmin>
      <PageHeader
        title="Status"
        description="Connection and configuration for this local install."
      />
      <StatusView />
    </RequireAdmin>
  );
}
