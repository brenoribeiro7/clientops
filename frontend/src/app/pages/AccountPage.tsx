import { useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";

export function AccountPage() {
  const { session, logout } = useAuth();
  const navigate = useNavigate();
  if (!session) return null;
  return (
    <section className="foundation-card">
      <p className="eyebrow">Minha conta</p>
      <h1>{session.user.name}</h1>
      <dl className="details-list">
        <div>
          <dt>E-mail</dt>
          <dd>{session.user.email}</dd>
        </div>
        <div>
          <dt>Perfil</dt>
          <dd>{session.user.role === "ADMIN" ? "Administrador" : "Técnico"}</dd>
        </div>
      </dl>
      <button
        className="button button--secondary"
        type="button"
        onClick={() => void logout().then(() => navigate("/login", { replace: true }))}
      >
        Sair
      </button>
    </section>
  );
}
