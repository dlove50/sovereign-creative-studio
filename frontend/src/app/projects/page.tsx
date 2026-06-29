import { PageHeader } from "@/components/page-header";
import { ProjectsView } from "@/components/projects-view";

export default function ProjectsPage() {
  return (
    <>
      <PageHeader
        title="Projects"
        description="Group related generations into projects."
      />
      <ProjectsView />
    </>
  );
}
