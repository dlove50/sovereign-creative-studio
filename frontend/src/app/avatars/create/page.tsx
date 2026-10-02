import { PageHeader } from "@/components/page-header";
import { AvatarsView } from "@/components/avatars-view";

export default function MakeVideoPage() {
  return (
    <>
      <PageHeader
        title="Make a video"
        description="Write a script, pick a voice and a look, and your avatar says it."
      />
      <AvatarsView />
    </>
  );
}
