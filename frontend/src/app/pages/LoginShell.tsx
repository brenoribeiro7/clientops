import { Link } from "react-router-dom";

import { SkipLink } from "../../components/shared/SkipLink";

export function LoginShell() {
  return (
    <div className="public-shell">
      <SkipLink />
      <header className="public-header">
        <Link className="brand" to="/login" aria-label="ClientOps — início">
          ClientOps
        </Link>
      </header>
      <main id="main-content" className="public-main">
        <section className="foundation-card" aria-labelledby="login-title">
          <p className="eyebrow">Acesso interno</p>
          <h1 id="login-title">Acesso ao ClientOps</h1>
          <p className="foundation-description">
            A autenticação será disponibilizada na próxima fase da implementação.
          </p>
        </section>
      </main>
    </div>
  );
}
