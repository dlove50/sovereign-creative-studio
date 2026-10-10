export function PageHeader({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <header className="page-heading-enter mb-8 max-w-reading">
      <h1 className="text-2xl font-semibold tracking-[-0.025em] md:text-3xl">
        {title}
      </h1>
      {description && (
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground md:text-[0.9375rem]">{description}</p>
      )}
    </header>
  );
}
