import { PageHeader } from "@/components/page-header";
import { PoseStudioView } from "@/components/pose-studio-view";

export default function PoseStudioPage() {
  return (
    <>
      <PageHeader
        title="Pose Studio"
        description="Re-pose a subject with OpenPose presets or a reference image. Identity Pose uses IPAdapter for preservation; Stylized Pose remains available as the approximate fallback."
      />
      <PoseStudioView />
    </>
  );
}
