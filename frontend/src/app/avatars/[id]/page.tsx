import { AvatarDetailView } from "@/components/avatars/avatar-detail-view";

export default function AvatarPage({ params }: { params: { id: string } }) {
  return <AvatarDetailView avatarId={params.id} />;
}
