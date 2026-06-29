import { PageHeader } from "@/components/page-header";
import { ProjectWorkspaceView } from "@/components/project-workspace-view";

export default function ProjectWorkspacePage({
  params,
}: {
  params: { id: string };
}) {
  return (
    <>
      <PageHeader
        title="Project Workspace"
        description="Review uploads, scenes, copy, videos, and exports for one project."
      />
      <ProjectWorkspaceView projectId={params.id} />
    </>
  );
}
