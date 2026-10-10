import { Suspense } from "react";

import { DirectorBriefView } from "@/components/director/director-brief-view";

export default function DirectorNewPage() {
  return (
    <Suspense fallback={null}>
      <DirectorBriefView />
    </Suspense>
  );
}
