import { PageHeader } from "@/components/page-header";
import { CampaignsView } from "@/components/campaigns-view";

export default function CampaignsPage() {
  return (
    <>
      <PageHeader
        title="Campaigns"
        description="Pick a campaign style and generate a matching product scene and copy in one go."
      />
      <CampaignsView />
    </>
  );
}
