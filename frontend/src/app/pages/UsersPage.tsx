import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { apiRequest, type UserData, type UserPage } from "../../lib/api";
import { useAuth } from "../auth/AuthProvider";

type UserList = { page: UserPage; etags: Map<string, string> };

export function UsersPage() {
  const { session } = useAuth();
  const queryClient = useQueryClient();
  const [secret, setSecret] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["users"],
    queryFn: async (): Promise<UserList> => {
      const list = await apiRequest<UserPage>("/users?page_size=100");
      const etags = new Map<string, string>();
      await Promise.all(
        list.data.data.map(async (user) => {
          const detail = await apiRequest<{ data: UserData }>(`/users/${user.id}`);
          etags.set(user.id, detail.response.headers.get("ETag") ?? "");
        }),
      );
      return { page: list.data, etags };
    },
  });
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const result = await apiRequest<{ data: UserData; temporary_password: string }>(
      "/users",
      {
        method: "POST",
        body: JSON.stringify({ name: form.get("name"), email: form.get("email") }),
      },
      session.csrf_token,
    );
    setSecret(result.data.temporary_password);
    formElement.reset();
    await queryClient.invalidateQueries({ queryKey: ["users"] });
  }
  async function act(user: UserData, action: "disable" | "enable" | "reset-password") {
    if (!session || !query.data) return;
    const result = await apiRequest<{
      data: UserData;
      temporary_password?: string;
    }>(
      `/users/${user.id}/${action}`,
      {
        method: "POST",
        headers: { "If-Match": query.data.etags.get(user.id) ?? "" },
        body: JSON.stringify({}),
      },
      session.csrf_token,
    );
    if (result.data.temporary_password) setSecret(result.data.temporary_password);
    await queryClient.invalidateQueries({ queryKey: ["users"] });
  }
  return (
    <section>
      <p className="eyebrow">Configurações</p>
      <h1>Usuários</h1>
      <form className="inline-form" onSubmit={(event) => void create(event)}>
        <label>
          Nome
          <input name="name" required />
        </label>
        <label>
          E-mail
          <input name="email" type="email" required />
        </label>
        <button className="button" type="submit">
          Criar técnico
        </button>
      </form>
      {secret && (
        <div className="secret-card" role="status">
          <strong>Senha temporária — exibida uma vez</strong>
          <code>{secret}</code>
          <div className="button-row">
            <button
              className="button"
              type="button"
              onClick={() => void navigator.clipboard.writeText(secret)}
            >
              Copiar
            </button>
            <button
              className="button button--secondary"
              type="button"
              onClick={() => setSecret(null)}
            >
              Fechar
            </button>
          </div>
        </div>
      )}
      {query.isPending && <p>Carregando usuários…</p>}
      {query.isError && <p role="alert">Não foi possível carregar usuários.</p>}
      <div className="user-list">
        {query.data?.page.data.map((user) => (
          <article className="user-row" key={user.id}>
            <div>
              <strong>{user.name}</strong>
              <span>
                {user.email} · {user.status}
              </span>
            </div>
            {user.id !== session?.user.id && (
              <div className="button-row">
                <button
                  className="button button--secondary"
                  type="button"
                  onClick={() => void act(user, user.status === "ACTIVE" ? "disable" : "enable")}
                >
                  {user.status === "ACTIVE" ? "Desabilitar" : "Habilitar"}
                </button>
                <button
                  className="button button--secondary"
                  type="button"
                  onClick={() => void act(user, "reset-password")}
                >
                  Redefinir senha
                </button>
              </div>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
