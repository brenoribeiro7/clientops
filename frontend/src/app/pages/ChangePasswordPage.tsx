import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";

export function ChangePasswordPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  if (!auth.loading && !auth.session) return <Navigate to="/login" replace />;
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const session = await auth.changePassword(
        String(form.get("currentPassword")),
        String(form.get("newPassword")),
      );
      navigate(session.user.role === "ADMIN" ? "/admin" : "/tech/today", { replace: true });
    } catch {
      setError("Revise a senha atual e os requisitos da nova senha.");
    }
  }
  return (
    <main id="main-content" className="auth-page">
      <form className="form-card" onSubmit={submit}>
        <p className="eyebrow">Segurança</p>
        <h1>Troque sua senha temporária</h1>
        <label>
          Senha atual
          <input name="currentPassword" type="password" autoComplete="current-password" required />
        </label>
        <label>
          Nova senha
          <input name="newPassword" type="password" autoComplete="new-password" required />
        </label>
        <p className="field-help">Use de 15 a 128 caracteres.</p>
        {error && <p role="alert">{error}</p>}
        <button className="button" type="submit">
          Salvar nova senha
        </button>
      </form>
    </main>
  );
}
