import { Suspense } from "react";

import { AddLooksView } from "@/components/avatars/add-looks-view";

export default function AddLooksPage() {
  return (
    <Suspense fallback={null}>
      <AddLooksView />
    </Suspense>
  );
}
