type FoundationPageProps = {
  eyebrow: string;
  title: string;
  description: string;
};

export function FoundationPage({ eyebrow, title, description }: FoundationPageProps) {
  return (
    <section className="foundation-card" aria-labelledby="foundation-title">
      <p className="eyebrow">{eyebrow}</p>
      <h1 id="foundation-title">{title}</h1>
      <p className="foundation-description">{description}</p>
      <p className="foundation-note">Estrutura inicial do ClientOps.</p>
    </section>
  );
}
