import { PageHeader } from "@/components/page-header";
import { GalleryView } from "@/components/gallery-view";

export default function GalleryPage() {
  return (
    <>
      <PageHeader
        title="Gallery"
        description="Every generation you've created, newest first."
      />
      <GalleryView />
    </>
  );
}
