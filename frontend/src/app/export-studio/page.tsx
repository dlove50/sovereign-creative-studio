import { ExportStudioView } from "@/components/export-studio-view";
import { PageHeader } from "@/components/page-header";

export default function ExportStudioPage() {
  return (
    <>
      <PageHeader
        title="Export Studio"
        description="Package project scenes, copy, videos, briefs, and brand kits into downloadable campaign ZIPs."
      />
      <ExportStudioView />
    </>
  );
}
