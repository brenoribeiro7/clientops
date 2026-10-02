import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { clientKeys, getTimeline } from "./api";
import { Pagination } from "./Pagination";

export function TimelineSection({ clientId }: { clientId: string }) {
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: clientKeys.timeline(clientId, page),
    queryFn: ({ signal }) => getTimeline(clientId, page, signal),
  });
  return (
    <section className="detail-section" aria-labelledby="timeline-heading">
      <h2 id="timeline-heading">Histórico</h2>
      {query.isPending && <p aria-live="polite">Carregando histórico…</p>}
      {query.isError && (
        <div role="alert">
          <p>Não foi possível carregar o histórico.</p>
          <button className="button button--secondary" onClick={() => void query.refetch()}>
            Tentar novamente
          </button>
        </div>
      )}
      {query.data?.data.length === 0 && <p>Nenhum evento registrado.</p>}
      <ol className="timeline-list">
        {query.data?.data.map((event) => (
          <li key={event.id}>
            <strong>{event.event_type}</strong>
            <span>{new Date(event.occurred_at).toLocaleString("pt-BR")}</span>
            <span>por {event.actor.display_name}</span>
          </li>
        ))}
      </ol>
      {query.data && (
        <Pagination page={query.data.page} onChange={setPage} label="Paginação do histórico" />
      )}
    </section>
  );
}
