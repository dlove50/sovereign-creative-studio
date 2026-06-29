import { PageHeader } from "@/components/page-header";
import { AdminBackupsView } from "@/components/admin-backups-view";

export default function AdminBackupsPage() {
  return (
    <>
      <PageHeader
        title="Backup & Recovery"
        description="Local/private snapshots of the database, storage, and workflow config. Restore is manual for safety."
      />
      <AdminBackupsView />
    </>
  );
}
