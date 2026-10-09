import { Suspense } from "react";
import { PageHeader } from "@/components/page-header";
import { VideosView } from "@/components/videos-view";

export default function VideosPage() {
  return (
    <>
      <PageHeader
        title="Videos"
        description="Turn a completed product scene into a short motion clip with the configured video backend."
      />
      <Suspense fallback={<p>Loading video studio…</p>}>
        <VideosView />
      </Suspense>
    </>
  );
}
