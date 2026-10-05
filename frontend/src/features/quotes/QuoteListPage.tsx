import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { Pagination } from "../clients/Pagination";
import { listQuotes, quoteKeys, type QuoteListParams } from "./api";

function paramsFrom(search: URLSearchParams): QuoteListParams {
  const statuses = ["DRAFT", "SENT", "APPROVED", "CANCELLED"] as const;
  const sorts = [
    "number",
    "-number",
    "created_at",
    "-created_at",
    "valid_until",
    "-valid_until",
  ] as const;
  const status = statuses.find((value) => value === search.get("status"));
  return {
    page: Math.max(1, Number(search.get("page") ?? 1) || 1),
    status,
    q: search.get("q") ?? undefined,
    sort: sorts.find((value) => value === search.get("sort")) ?? "-created_at",
  };
}

export default function QuoteListPage() {
  const [search, setSearch] = useSearchParams();
  const params = paramsFrom(search);
  const [searchValue, setSearchValue] = useState(params.q ?? "");
  const query = useQuery({
    queryKey: quoteKeys.list(params),
    queryFn: ({ signal }) => listQuotes(params, signal),
  });

  function update(changes: Partial<QuoteListParams>) {
    const next = { ...params, ...changes };
    const value = new URLSearchParams();
    if (next.page > 1) value.set("page", String(next.page));
    if (next.status) value.set("status", next.status);
    if (next.q) value.set("q", next.q);
    if (next.sort !== "-created_at") value.set("sort", next.sort);
    setSearch(value);
  }

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    const cleaned = searchValue.trim();
    update({ q: cleaned.length >= 2 ? cleaned : undefined, page: 1 });
  }

  return (
    <section className="quotes-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Comercial</p>
          <h1>Orçamentos</h1>
          <p className="foundation-description">Prepare, envie e acompanhe propostas.</p>
        </div>
        <Link className="button" to="/admin/quotes/new">
          Novo orçamento
        </Link>
      </div>
      <div className="filters">
        <form className="search-form" role="search" onSubmit={submitSearch}>
          <label>
            Buscar por número ou item
            <input
              minLength={2}
              maxLength={100}
              value={searchValue}
              onChange={(event) => setSearchValue(event.target.value)}
            />
          </label>
          <button className="button button--secondary">Buscar</button>
        </form>
        <label>
          Status
          <select
            value={params.status ?? ""}
            onChange={(event) =>
              update({
                status: (event.target.value || undefined) as QuoteListParams["status"],
                page: 1,
              })
            }
          >
            <option value="">Todos</option>
            <option value="DRAFT">Rascunho</option>
            <option value="SENT">Enviado</option>
            <option value="APPROVED">Aprovado</option>
            <option value="CANCELLED">Cancelado</option>
          </select>
        </label>
        <label>
          Ordenar
          <select
            value={params.sort}
            onChange={(event) =>
              update({ sort: event.target.value as QuoteListParams["sort"], page: 1 })
            }
          >
            <option value="-created_at">Mais recentes</option>
            <option value="created_at">Mais antigos</option>
            <option value="-number">Maior número</option>
            <option value="number">Menor número</option>
            <option value="valid_until">Validade próxima</option>
          </select>
        </label>
      </div>
      {query.isPending && <div className="skeleton">Carregando orçamentos…</div>}
      {query.isError && (
        <div className="empty-state" role="alert">
          Não foi possível carregar os orçamentos.
        </div>
      )}
      {query.data?.data.length === 0 && (
        <div className="empty-state">
          <h2>Nenhum orçamento encontrado</h2>
          <p>Crie um rascunho ou revise os filtros.</p>
        </div>
      )}
      <ul className="resource-list quotes-list">
        {query.data?.data.map((quote) => (
          <li className="resource-card quote-card" key={quote.id}>
            <div className="resource-card__main">
              <Link className="resource-link" to={`/admin/quotes/${quote.id}`}>
                {quote.number}
              </Link>
              <span>Validade: {quote.valid_until}</span>
              <span>Total: R$ {quote.total.replace(".", ",")}</span>
            </div>
            <span className={`status-badge status-badge--${quote.status.toLowerCase()}`}>
              {quote.is_expired ? "Vencido" : quote.status}
            </span>
          </li>
        ))}
      </ul>
      {query.data && (
        <Pagination
          page={query.data.page}
          label="Paginação de orçamentos"
          onChange={(page) => update({ page })}
        />
      )}
    </section>
  );
}
