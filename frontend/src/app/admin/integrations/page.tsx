import { PageHeader } from "@/components/page-header";
import { AdminIntegrationsView } from "@/components/admin-integrations-view";

export default function AdminIntegrationsPage() {
  return (
    <>
      <PageHeader
        title="Provider Integrations"
        description="Optional premium cloud providers. Local models remain the default engine."
      />
      <AdminIntegrationsView />
    </>
  );
}
