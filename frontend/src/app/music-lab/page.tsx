import { Suspense } from "react";

import { MusicLabView } from "@/components/music/music-lab-view";

export default function MusicLabPage() {
  return (
    <Suspense fallback={null}>
      <MusicLabView />
    </Suspense>
  );
}
