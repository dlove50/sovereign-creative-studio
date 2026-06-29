import { AdminDashboardView } from "@/components/admin-dashboard-view";
import { PageHeader } from "@/components/page-header";

export default function AdminPage() {
  return (
    <>
      <PageHeader
        title="Admin Dashboard"
        description="Private local/family studio controls, health, usage, credits, and safe workflow defaults."
      />
      <AdminDashboardView />
    </>
  );
}
