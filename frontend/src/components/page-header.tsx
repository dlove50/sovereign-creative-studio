export function PageHeader({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <div className="mb-8 animate-fade-up">
      <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
        {title}
      </h1>
      {description && (
        <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      )}
    </div>
  );
}
