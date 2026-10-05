import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { useAuth } from "../../app/auth/AuthProvider";
import type { ClientData } from "../../lib/api";
import { clientKeys, listClients, mutate, type ListParams } from "./api";
import { ClientForm } from "./ClientForm";
import { Pagination } from "./Pagination";
import { StatusBadge } from "./StatusBadge";

function fromSearch(search: URLSearchParams): ListParams {
  const status = search.get("status") === "ARCHIVED" ? "ARCHIVED" : "ACTIVE";
  const sorts = ["name", "-name", "created_at", "-created_at"] as const;
  const requestedSort = search.get("sort");
  return {
    page: Math.max(1, Number(search.get("page") ?? 1) || 1),
    pageSize: 20,
    status,
    q: search.get("q") ?? undefined,
    sort: sorts.find((value) => value === requestedSort) ?? "-created_at",
  };
}

export default function ClientListPage() {
  const { session } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [search, setSearch] = useSearchParams();
  const [showCreate, setShowCreate] = useState(false);
  const params = fromSearch(search);
  const query = useQuery({
    queryKey: clientKeys.list(params),
    queryFn: ({ signal }) => listClients(params, signal),
  });

  function update(next: Partial<ListParams>) {
    const value = { ...params, ...next };
    const result = new URLSearchParams();
    if (value.page > 1) result.set("page", String(value.page));
    if (value.status !== "ACTIVE") result.set("status", value.status);
    if (value.q) result.set("q", value.q);
    if (value.sort !== "-created_at") result.set("sort", value.sort);
    setSearch(result);
  }

  function searchClients(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const q = String(new FormData(event.currentTarget).get("q") ?? "").trim();
    update({ q: q.length >= 2 ? q : undefined, page: 1 });
  }

  async function create(payload: Record<string, unknown>) {
    if (!session) return;
    const result = await mutate<ClientData>("/clients", "POST", payload, session.csrf_token);
    await queryClient.invalidateQueries({ queryKey: clientKeys.all });
    navigate(`/admin/clients/${result.value.id}`);
  }

  return (
    <section className="clients-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Cadastros</p>
          <h1>Clientes</h1>
          <p className="foundation-description">Consulte clientes e seus equipamentos.</p>
        </div>
        <button className="button" type="button" onClick={() => setShowCreate(true)}>
          Cadastrar cliente
        </button>
      </div>
      {showCreate && (
        <section aria-labelledby="new-client-heading">
          <h2 id="new-client-heading">Novo cliente</h2>
          <ClientForm
            submitLabel="Cadastrar cliente"
            onSubmit={create}
            onCancel={() => setShowCreate(false)}
          />
        </section>
      )}
      <div className="filters">
        <form className="search-form" role="search" onSubmit={searchClients}>
          <label>
            Buscar por nome
            <input name="q" minLength={2} maxLength={100} defaultValue={params.q ?? ""} />
          </label>
          <button className="button button--secondary">Buscar</button>
        </form>
        <label>
          Status
          <select
            value={params.status}
            onChange={(event) =>
              update({ status: event.target.value as ListParams["status"], page: 1 })
            }
          >
            <option value="ACTIVE">Ativos</option>
            <option value="ARCHIVED">Arquivados</option>
          </select>
        </label>
        <label>
          Ordenar
          <select
            value={params.sort}
            onChange={(event) =>
              update({ sort: event.target.value as ListParams["sort"], page: 1 })
            }
          >
            <option value="-created_at">Mais recentes</option>
            <option value="created_at">Mais antigos</option>
            <option value="name">Nome A–Z</option>
            <option value="-name">Nome Z–A</option>
          </select>
        </label>
      </div>
      {query.isPending && (
        <div className="skeleton" aria-live="polite">
          Carregando clientes…
        </div>
      )}
      {query.isError && (
        <div className="empty-state" role="alert">
          <p>Não foi possível carregar os clientes.</p>
          <button className="button button--secondary" onClick={() => void query.refetch()}>
            Tentar novamente
          </button>
        </div>
      )}
      {query.data?.data.length === 0 && (
        <div className="empty-state">
          <h2>{params.q ? "Nenhum cliente encontrado" : "Nenhum cliente neste status"}</h2>
          <p>
            {params.q ? "Revise a busca ou limpe os filtros." : "Cadastre um cliente para começar."}
          </p>
          {params.q && (
            <button
              className="button button--secondary"
              onClick={() => update({ q: undefined, page: 1 })}
            >
              Limpar busca
            </button>
          )}
        </div>
      )}
      <ul className="resource-list clients-list">
        {query.data?.data.map((client) => (
          <li className="resource-card" key={client.id}>
            <div className="resource-card__main">
              <Link className="resource-link" to={`/admin/clients/${client.id}`}>
                {client.name}
              </Link>
              {client.phone && <span>{client.phone}</span>}
              {client.email && <span>{client.email}</span>}
            </div>
            <StatusBadge status={client.status} />
          </li>
        ))}
      </ul>
      {query.data && (
        <Pagination
          page={query.data.page}
          label="Paginação de clientes"
          onChange={(page) => update({ page })}
        />
      )}
    </section>
  );
}
