import { AssetsLibraryView } from "@/components/assets-library-view";
import { PageHeader } from "@/components/page-header";

export default function AssetsLibraryPage() {
  return (
    <>
      <PageHeader
        title="Asset Library"
        description="Browse uploads, product scenes, copy, videos, and downloadable outputs from one place."
      />
      <AssetsLibraryView />
    </>
  );
}
