import { PageHeader } from "@/components/page-header";
import { ProfileView } from "@/components/profile-view";

export default function ProfilePage() {
  return (
    <>
      <PageHeader title="Profile" description="Your account and session." />
      <ProfileView />
    </>
  );
}
