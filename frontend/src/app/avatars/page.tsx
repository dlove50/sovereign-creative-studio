import { PageHeader } from "@/components/page-header";
import { AvatarsView } from "@/components/avatars-view";

export default function AvatarsPage() {
  return (
    <>
      <PageHeader
        title="Avatars & Voices"
        description="Create a talking avatar from a video or photo, then add a voice."
      />
      <AvatarsView />
    </>
  );
}
