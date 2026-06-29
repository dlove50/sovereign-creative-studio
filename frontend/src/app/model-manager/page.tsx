import { ModelManagerView } from "@/components/model-manager-view";
import { PageHeader } from "@/components/page-header";
import { RequireAdmin } from "@/components/require-admin";

export default function ModelManagerPage() {
  return (
    <RequireAdmin>
      <PageHeader
        title="Model Manager"
        description="Installed models, active backends, product-scene model selection, ComfyUI reachability, and workflow readiness."
      />
      <ModelManagerView />
    </RequireAdmin>
  );
}
