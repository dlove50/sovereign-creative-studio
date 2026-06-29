import { PageHeader } from "@/components/page-header";
import { CampaignBuilderView } from "@/components/campaign-builder-view";

export default function CampaignBuilderPage() {
  return (
    <>
      <PageHeader
        title="Campaign Builder"
        description="Generate a full campaign — scenes, copy, and a video — from one project, brief, and asset."
      />
      <CampaignBuilderView />
    </>
  );
}
