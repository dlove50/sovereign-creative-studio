import { PageHeader } from "@/components/page-header";
import { InspirationGallery } from "@/components/inspiration-gallery";

export default function InspirationPage() {
  return (
    <>
      <PageHeader
        title="Inspiration"
        description="Browse trending ideas and ready-made templates to start from."
      />
      <InspirationGallery />
    </>
  );
}
