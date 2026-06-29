import { PageHeader } from "@/components/page-header";
import { CopyStudioView } from "@/components/copy-studio-view";

export default function CopyStudioPage() {
  return (
    <>
      <PageHeader
        title="Copy Studio"
        description="Generate on-brand marketing copy for your products and ad scenes."
      />
      <CopyStudioView />
    </>
  );
}
