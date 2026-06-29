import { AssetCollectionsView } from "@/components/asset-collections-view";
import { PageHeader } from "@/components/page-header";

export default function CollectionsPage() {
  return (
    <>
      <PageHeader
        title="Asset Collections"
        description="Group product assets and launch multi-asset campaigns from one creative brief."
      />
      <AssetCollectionsView />
    </>
  );
}
