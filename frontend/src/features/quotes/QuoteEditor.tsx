import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import type { QuoteDetail } from "../../lib/api";
import { clientKeys, listClients } from "../clients/api";

type DraftItem = {
  id?: string;
  description: string;
  quantity: string;
  unit_price: string;
};

type Props = {
  initial?: QuoteDetail;
  submitLabel: string;
  onSubmit: (payload: Record<string, unknown>) => Promise<void>;
  onCancel?: () => void;
  onReload?: () => void;
};

export function QuoteEditor({ initial, submitLabel, onSubmit, onCancel, onReload }: Props) {
  const clients = useQuery({
    queryKey: clientKeys.list({
      page: 1,
      pageSize: 100,
      status: "ACTIVE",
      sort: "name",
    }),
    queryFn: ({ signal }) =>
      listClients({ page: 1, pageSize: 100, status: "ACTIVE", sort: "name" }, signal),
  });
  const [clientId, setClientId] = useState(initial?.client_id ?? "");
  const [validUntil, setValidUntil] = useState(initial?.valid_until ?? "");
  const [notes, setNotes] = useState(initial?.notes ?? "");
  const [items, setItems] = useState<DraftItem[]>(
    initial?.items.map((item) => ({
      id: item.id,
      description: item.description,
      quantity: item.quantity,
      unit_price: item.unit_price,
    })) ?? [],
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function updateItem(index: number, patch: Partial<DraftItem>) {
    setItems((current) =>
      current.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)),
    );
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await onSubmit({
        client_id: clientId,
        valid_until: validUntil,
        notes: notes.trim() || null,
        items: items.map((item, index) => ({
          ...(item.id ? { id: item.id } : {}),
          position: index + 1,
          description: item.description,
          quantity: item.quantity,
          unit_price: item.unit_price,
        })),
      });
    } catch (caught) {
      const conflict =
        typeof caught === "object" &&
        caught !== null &&
        "status" in caught &&
        caught.status === 412;
      setError(
        conflict
          ? "Este orçamento mudou em outra sessão. Seu formulário foi preservado; recarregue antes de salvar novamente."
          : "Não foi possível salvar o orçamento. Revise os campos.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="inline-form quote-editor" onSubmit={(event) => void submit(event)}>
      <div className="form-grid">
        <label>
          Cliente ativo
          <select required value={clientId} onChange={(event) => setClientId(event.target.value)}>
            <option value="">Selecione</option>
            {clients.data?.data.map((client) => (
              <option key={client.id} value={client.id}>
                {client.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Validade
          <input
            required
            type="date"
            value={validUntil}
            onChange={(event) => setValidUntil(event.target.value)}
          />
        </label>
      </div>
      <label>
        Observações da proposta
        <textarea
          maxLength={5000}
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
        />
      </label>
      <fieldset className="quote-items">
        <legend>Itens</legend>
        {items.map((item, index) => (
          <div className="quote-item-editor" key={item.id ?? `new-${index}`}>
            <label className="quote-item-editor__description">
              Descrição do item {index + 1}
              <input
                required
                maxLength={500}
                value={item.description}
                onChange={(event) => updateItem(index, { description: event.target.value })}
              />
            </label>
            <label>
              Quantidade
              <input
                required
                inputMode="decimal"
                pattern="(?:0|[1-9][0-9]{0,3})(?:\.[0-9]{1,3})?"
                value={item.quantity}
                onChange={(event) => updateItem(index, { quantity: event.target.value })}
              />
            </label>
            <label>
              Preço unitário
              <input
                required
                inputMode="decimal"
                pattern="(?:0|[1-9][0-9]{0,6})\.[0-9]{2}"
                value={item.unit_price}
                onChange={(event) => updateItem(index, { unit_price: event.target.value })}
              />
            </label>
            <button
              className="button button--secondary"
              type="button"
              onClick={() =>
                setItems((current) => current.filter((_, itemIndex) => itemIndex !== index))
              }
            >
              Remover item {index + 1}
            </button>
          </div>
        ))}
        <button
          className="button button--secondary"
          type="button"
          disabled={items.length >= 100}
          onClick={() =>
            setItems((current) => [
              ...current,
              { description: "", quantity: "1.000", unit_price: "0.00" },
            ])
          }
        >
          Adicionar item
        </button>
      </fieldset>
      {initial && (
        <p className="authoritative-total">
          Total calculado pelo servidor: <strong>R$ {initial.total.replace(".", ",")}</strong>
        </p>
      )}
      {error && (
        <div className="status-message status-message--error" role="alert">
          <p>{error}</p>
          {onReload && error.includes("preservado") && (
            <button className="button button--secondary" type="button" onClick={onReload}>
              Recarregar versão atual
            </button>
          )}
        </div>
      )}
      <div className="button-row">
        <button className="button" disabled={busy}>
          {busy ? "Salvando…" : submitLabel}
        </button>
        {onCancel && (
          <button className="button button--secondary" type="button" onClick={onCancel}>
            Cancelar edição
          </button>
        )}
      </div>
    </form>
  );
}
