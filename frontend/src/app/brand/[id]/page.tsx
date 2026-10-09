import { BrandVisualsView } from "@/components/brand/brand-visuals-view";

export default function BrandVisualsPage({ params }: { params: { id: string } }) {
  return <BrandVisualsView projectId={params.id} />;
}
