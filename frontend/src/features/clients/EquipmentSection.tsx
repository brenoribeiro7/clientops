import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import type { EquipmentData } from "../../lib/api";
import { useAuth } from "../../app/auth/AuthProvider";
import {
  clientKeys,
  getEquipment,
  listEquipment,
  mutate,
  type ListParams,
  type Resource,
} from "./api";
import { ConfirmStatusDialog } from "./ConfirmStatusDialog";
import { EquipmentForm, type EquipmentPayload } from "./EquipmentForm";
import { Pagination } from "./Pagination";
import { StatusBadge } from "./StatusBadge";

type Props = { clientId: string; clientArchived: boolean };

export function EquipmentSection({ clientId, clientArchived }: Props) {
  const { session } = useAuth();
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState<Resource<EquipmentData> | null>(null);
  const [params, setParams] = useState<ListParams>({
    page: 1,
    pageSize: 20,
    status: "ACTIVE",
    sort: "name",
  });
  const query = useQuery({
    queryKey: clientKeys.equipment(clientId, params),
    queryFn: ({ signal }) => listEquipment(clientId, params, signal),
  });

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["clients", clientId, "equipment"] });
    await queryClient.invalidateQueries({ queryKey: ["clients", clientId, "timeline"] });
  }

  async function create(payload: EquipmentPayload) {
    if (!session) return;
    await mutate<EquipmentData>(
      `/clients/${clientId}/equipment`,
      "POST",
      payload,
      session.csrf_token,
    );
    setShowCreate(false);
    await refresh();
  }

  async function save(payload: EquipmentPayload) {
    if (!session || !editing) return;
    const result = await mutate<EquipmentData>(
      `/clients/${clientId}/equipment/${editing.value.id}`,
      "PATCH",
      payload,
      session.csrf_token,
      editing.etag,
    );
    setEditing(result);
    setEditing(null);
    await refresh();
  }

  async function loadForEdit(equipmentId: string) {
    setEditing(await getEquipment(clientId, equipmentId));
    setShowCreate(false);
  }

  async function act(equipmentId: string, version: number, action: "archive" | "restore") {
    if (!session) return;
    await mutate<EquipmentData>(
      `/clients/${clientId}/equipment/${equipmentId}/${action}`,
      "POST",
      {},
      session.csrf_token,
      `"v${version}"`,
    );
    await refresh();
  }

  return (
    <section className="detail-section" aria-labelledby="equipment-heading">
      <div className="section-heading">
        <div>
          <h2 id="equipment-heading">Equipamentos</h2>
          {clientArchived && (
            <p className="field-help" id="archived-client-equipment-help">
              Restaure o cliente para adicionar novos equipamentos.
            </p>
          )}
        </div>
        <button
          className="button"
          type="button"
          disabled={clientArchived}
          aria-describedby={clientArchived ? "archived-client-equipment-help" : undefined}
          onClick={() => {
            setShowCreate(true);
            setEditing(null);
          }}
        >
          Adicionar equipamento
        </button>
      </div>
      <div className="filter-row">
        <label>
          Status dos equipamentos
          <select
            value={params.status}
            onChange={(event) =>
              setParams({ ...params, page: 1, status: event.target.value as ListParams["status"] })
            }
          >
            <option value="ACTIVE">Ativos</option>
            <option value="ARCHIVED">Arquivados</option>
          </select>
        </label>
      </div>
      {showCreate && (
        <EquipmentForm
          submitLabel="Adicionar equipamento"
          onSubmit={create}
          onCancel={() => setShowCreate(false)}
        />
      )}
      {editing && (
        <EquipmentForm
          key={`${editing.value.id}-${editing.etag}`}
          initial={editing.value}
          submitLabel="Salvar equipamento"
          onSubmit={save}
          onCancel={() => setEditing(null)}
          onReload={() => void loadForEdit(editing.value.id)}
        />
      )}
      {query.isPending && <p aria-live="polite">Carregando equipamentos…</p>}
      {query.isError && (
        <div role="alert">
          <p>Não foi possível carregar os equipamentos.</p>
          <button className="button button--secondary" onClick={() => void query.refetch()}>
            Tentar novamente
          </button>
        </div>
      )}
      {query.data?.data.length === 0 && <p>Nenhum equipamento neste status.</p>}
      <ul className="resource-list">
        {query.data?.data.map((equipment) => (
          <li className="resource-card" key={equipment.id}>
            <div className="resource-card__main">
              <strong>{equipment.name}</strong>
              <span>
                {[equipment.brand, equipment.model].filter(Boolean).join(" · ") ||
                  "Sem marca/modelo"}
              </span>
              {equipment.serial_number && <span>Série: {equipment.serial_number}</span>}
              {equipment.location_description && <span>{equipment.location_description}</span>}
            </div>
            <StatusBadge status={equipment.status} />
            <div className="button-row">
              <button
                className="button button--secondary"
                type="button"
                onClick={() => void loadForEdit(equipment.id)}
              >
                Editar
              </button>
              <ConfirmStatusDialog
                action={equipment.status === "ACTIVE" ? "Arquivar" : "Restaurar"}
                description={`Confirme a alteração de status de ${equipment.name}.`}
                onConfirm={() =>
                  void act(
                    equipment.id,
                    equipment.version,
                    equipment.status === "ACTIVE" ? "archive" : "restore",
                  )
                }
              />
            </div>
          </li>
        ))}
      </ul>
      {query.data && (
        <Pagination
          page={query.data.page}
          label="Paginação dos equipamentos"
          onChange={(page) => setParams({ ...params, page })}
        />
      )}
    </section>
  );
}
