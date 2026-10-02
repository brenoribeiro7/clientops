import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useAuth } from "../../app/auth/AuthProvider";
import type { ClientData } from "../../lib/api";
import { clientKeys, getClient, mutate } from "./api";
import { ClientForm } from "./ClientForm";
import { ConfirmStatusDialog } from "./ConfirmStatusDialog";
import { EquipmentSection } from "./EquipmentSection";
import { StatusBadge } from "./StatusBadge";
import { TimelineSection } from "./TimelineSection";

export default function ClientDetailPage() {
  const { clientId = "" } = useParams();
  const { session } = useAuth();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [message, setMessage] = useState("");
  const query = useQuery({
    queryKey: clientKeys.detail(clientId),
    queryFn: ({ signal }) => getClient(clientId, signal),
  });

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: clientKeys.detail(clientId) });
    await queryClient.invalidateQueries({ queryKey: clientKeys.all });
    await queryClient.invalidateQueries({ queryKey: ["clients", clientId, "timeline"] });
  }

  async function save(payload: Record<string, unknown>) {
    if (!session || !query.data) return;
    await mutate<ClientData>(
      `/clients/${clientId}`,
      "PATCH",
      payload,
      session.csrf_token,
      query.data.etag,
    );
    setEditing(false);
    setMessage("Cliente salvo.");
    await refresh();
  }

  async function act(action: "archive" | "restore") {
    if (!session || !query.data) return;
    try {
      await mutate<ClientData>(
        `/clients/${clientId}/${action}`,
        "POST",
        {},
        session.csrf_token,
        query.data.etag,
      );
      setMessage(action === "archive" ? "Cliente arquivado." : "Cliente restaurado.");
      await refresh();
    } catch {
      setMessage("Não foi possível alterar o status. Recarregue a página.");
    }
  }

  if (query.isPending)
    return (
      <div className="skeleton" aria-live="polite">
        Carregando cliente…
      </div>
    );
  if (query.isError || !query.data) {
    return (
      <section className="empty-state" role="alert">
        <h1>Não foi possível carregar o cliente</h1>
        <button className="button button--secondary" onClick={() => void query.refetch()}>
          Tentar novamente
        </button>
      </section>
    );
  }
  const client = query.data.value;
  return (
    <div className="client-detail">
      <Link className="back-link" to="/admin/clients">
        ← Voltar para clientes
      </Link>
      <section className="detail-header">
        <div>
          <p className="eyebrow">Cliente</p>
          <h1>{client.name}</h1>
          <StatusBadge status={client.status} />
        </div>
        <div className="button-row">
          <button
            className="button button--secondary"
            type="button"
            onClick={() => setEditing(true)}
          >
            Editar cliente
          </button>
          <ConfirmStatusDialog
            action={client.status === "ACTIVE" ? "Arquivar" : "Restaurar"}
            description={
              client.status === "ACTIVE"
                ? "O histórico e os equipamentos serão preservados. Novos equipamentos ficarão bloqueados."
                : "O cliente voltará às seleções operacionais."
            }
            onConfirm={() => void act(client.status === "ACTIVE" ? "archive" : "restore")}
          />
        </div>
      </section>
      {message && (
        <p className="status-message" role="status">
          {message}
        </p>
      )}
      {editing ? (
        <section aria-labelledby="edit-client-heading">
          <h2 id="edit-client-heading">Editar cliente</h2>
          <ClientForm
            key={query.data.etag}
            initial={client}
            submitLabel="Salvar cliente"
            onSubmit={save}
            onCancel={() => setEditing(false)}
            onReload={() => void query.refetch()}
          />
        </section>
      ) : (
        <section className="detail-section" aria-labelledby="client-data-heading">
          <h2 id="client-data-heading">Informações</h2>
          <dl className="details-grid">
            <div>
              <dt>Telefone</dt>
              <dd>{client.phone ?? "Não informado"}</dd>
            </div>
            <div>
              <dt>E-mail</dt>
              <dd>{client.email ?? "Não informado"}</dd>
            </div>
            <div>
              <dt>Endereço</dt>
              <dd>{client.address ?? "Não informado"}</dd>
            </div>
            <div>
              <dt>Notas</dt>
              <dd>{client.notes ?? "Sem notas"}</dd>
            </div>
          </dl>
        </section>
      )}
      <EquipmentSection clientId={clientId} clientArchived={client.status === "ARCHIVED"} />
      <TimelineSection clientId={clientId} />
    </div>
  );
}
