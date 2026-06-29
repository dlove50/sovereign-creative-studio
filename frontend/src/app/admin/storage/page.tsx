import { PageHeader } from "@/components/page-header";
import { AdminStorageView } from "@/components/admin-storage-view";

export default function AdminStoragePage() {
  return (
    <>
      <PageHeader
        title="Storage Cleanup"
        description="Inspect local storage and run conservative dry-run-first cleanup for safe candidates."
      />
      <AdminStorageView />
    </>
  );
}
