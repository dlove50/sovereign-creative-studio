import { CreativeDirectorView } from "@/components/creative-director-view";
import { PageHeader } from "@/components/page-header";

export default function CreativeDirectorPage() {
  return (
    <>
      <PageHeader
        title="Creative Director"
        description="Get strategic campaign, scene, copy, video, and audience recommendations from project context."
      />
      <CreativeDirectorView />
    </>
  );
}
