import { useState, type FormEvent } from "react";

import { ApiError, type EquipmentData } from "../../lib/api";

export type EquipmentPayload = {
  name: string;
  brand: string | null;
  model: string | null;
  serial_number: string | null;
  location_description: string | null;
  notes: string | null;
};

type Props = {
  initial?: EquipmentData;
  submitLabel: string;
  onSubmit: (payload: EquipmentPayload) => Promise<void>;
  onCancel: () => void;
  onReload?: () => void;
};

function optional(form: FormData, name: string): string | null {
  const value = String(form.get(name) ?? "").trim();
  return value || null;
}

export function EquipmentForm({ initial, submitLabel, onSubmit, onCancel, onReload }: Props) {
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const [saving, setSaving] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError("");
    setConflict(false);
    setSaving(true);
    try {
      await onSubmit({
        name: String(form.get("name") ?? ""),
        brand: optional(form, "brand"),
        model: optional(form, "model"),
        serial_number: optional(form, "serialNumber"),
        location_description: optional(form, "location"),
        notes: optional(form, "notes"),
      });
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 412) {
        setConflict(true);
        setError("Este equipamento foi alterado em outra sessão. Seus dados foram preservados.");
      } else {
        setError(
          caught instanceof ApiError ? caught.message : "Não foi possível salvar o equipamento.",
        );
      }
    } finally {
      setSaving(false);
    }
  }
  return (
    <form className="form-card form-card--wide" onSubmit={(event) => void submit(event)}>
      {error && (
        <div className="form-error" role="alert">
          <p>{error}</p>
          {conflict && onReload && (
            <button className="button button--secondary" type="button" onClick={onReload}>
              Recarregar versão atual
            </button>
          )}
        </div>
      )}
      <label>
        Nome
        <input name="name" maxLength={160} defaultValue={initial?.name ?? ""} required />
      </label>
      <div className="form-grid">
        <label>
          Marca
          <input name="brand" maxLength={120} defaultValue={initial?.brand ?? ""} />
        </label>
        <label>
          Modelo
          <input name="model" maxLength={120} defaultValue={initial?.model ?? ""} />
        </label>
        <label>
          Número de série
          <input name="serialNumber" maxLength={100} defaultValue={initial?.serial_number ?? ""} />
        </label>
        <label>
          Localização
          <input
            name="location"
            maxLength={300}
            defaultValue={initial?.location_description ?? ""}
          />
        </label>
      </div>
      <label>
        Notas internas
        <textarea name="notes" maxLength={5000} defaultValue={initial?.notes ?? ""} />
      </label>
      <div className="button-row">
        <button className="button" disabled={saving} type="submit">
          {saving ? "Salvando…" : submitLabel}
        </button>
        <button className="button button--secondary" type="button" onClick={onCancel}>
          Cancelar
        </button>
      </div>
    </form>
  );
}
