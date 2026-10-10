import { Suspense } from "react";

import { DirectorProjectView } from "@/components/director/director-project-view";

export default function DirectorWatchPage() {
  return (
    <Suspense fallback={null}>
      <DirectorProjectView />
    </Suspense>
  );
}
