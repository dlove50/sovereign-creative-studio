import { PageHeader } from "@/components/page-header";
import { ProductionStudioView } from "@/components/production-studio-view";

export default function ProductionStudioPage() {
  return (
    <>
      <PageHeader
        title="Production Studio"
        description="Plan storyboards, shots, generated clips, sequence assembly, and production exports."
      />
      <ProductionStudioView />
    </>
  );
}
