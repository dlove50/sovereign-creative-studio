import { PageHeader } from "@/components/page-header";
import { WorkflowManagerView } from "@/components/workflow-manager-view";
import { RequireAdmin } from "@/components/require-admin";

export default function WorkflowManagerPage() {
  return (
    <RequireAdmin>
      <PageHeader
        title="Workflow Manager"
        description="Choose product-scene models, scene modes, video backends, copy providers, and workflows - no .env editing required."
      />
      <WorkflowManagerView />
    </RequireAdmin>
  );
}
