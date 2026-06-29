import { PageHeader } from "@/components/page-header";
import { AdminTopupsView } from "@/components/admin-topups-view";

export default function AdminTopupsPage() {
  return (
    <>
      <PageHeader
        title="Local Credit Top-Up"
        description="Grant local credits to family users. Local only — no real money, cards, or payment providers."
      />
      <AdminTopupsView />
    </>
  );
}
