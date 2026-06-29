import { PageHeader } from "@/components/page-header";
import { AdminJobsView } from "@/components/admin-jobs-view";

export default function AdminJobsPage() {
  return (
    <>
      <PageHeader
        title="Job Monitor"
        description="Local/private visibility into queued, running, completed, and failed generation jobs."
      />
      <AdminJobsView />
    </>
  );
}
