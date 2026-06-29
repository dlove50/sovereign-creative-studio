import { PageHeader } from "@/components/page-header";
import { PromptForm } from "@/components/prompt-form";

export default function CreatePage() {
  return (
    <>
      <PageHeader
        title="Create"
        description="Describe what you want and generate a result. Each generation costs credits."
      />
      <PromptForm />
    </>
  );
}
