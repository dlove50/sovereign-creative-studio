import { PageHeader } from "@/components/page-header";
import { UploadView } from "@/components/upload-view";

export default function UploadPage() {
  return (
    <>
      <PageHeader
        title="Upload"
        description="Add product images to a project and prepare them for product photography."
      />
      <UploadView />
    </>
  );
}
