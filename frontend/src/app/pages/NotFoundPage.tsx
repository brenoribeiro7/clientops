import { Link } from "react-router-dom";

export function NotFoundPage({ home }: { home: string }) {
  return (
    <section className="foundation-card" aria-labelledby="not-found-title">
      <p className="eyebrow">Página não encontrada</p>
      <h1 id="not-found-title">Não encontramos este endereço</h1>
      <p className="foundation-description">Confira o endereço ou retorne ao início.</p>
      <Link className="button button--link" to={home}>
        Voltar ao início
      </Link>
    </section>
  );
}
