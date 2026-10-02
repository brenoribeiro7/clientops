import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { ApiError } from "../../lib/api";
import { useAuth } from "../auth/AuthProvider";

export function LoginPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (!auth.loading && auth.session) {
    return <Navigate to={auth.session.user.role === "ADMIN" ? "/admin" : "/tech/today"} replace />;
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const session = await auth.login(String(form.get("email")), String(form.get("password")));
      navigate(
        session.user.must_change_password
          ? "/change-password"
          : session.user.role === "ADMIN"
            ? "/admin"
            : "/tech/today",
        { replace: true },
      );
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.code === "INVALID_CREDENTIALS"
          ? "E-mail ou senha inválidos."
          : "Não foi possível entrar agora.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <main id="main-content" className="auth-page">
      <form className="form-card" onSubmit={submit}>
        <p className="eyebrow">Acesso privado</p>
        <h1>Entrar no ClientOps</h1>
        <label>
          E-mail
          <input name="email" type="email" autoComplete="username" required />
        </label>
        <label>
          Senha
          <input name="password" type="password" autoComplete="current-password" required />
        </label>
        {error && <p role="alert">{error}</p>}
        <button className="button" disabled={busy} type="submit">
          {busy ? "Entrando…" : "Entrar"}
        </button>
      </form>
    </main>
  );
}
