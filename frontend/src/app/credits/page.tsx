import { PageHeader } from "@/components/page-header";
import { CreditsView } from "@/components/credits-view";

export default function CreditsPage() {
  return (
    <>
      <PageHeader title="Credits" description="Your credit balance and how credits are used." />
      <CreditsView />
    </>
  );
}
