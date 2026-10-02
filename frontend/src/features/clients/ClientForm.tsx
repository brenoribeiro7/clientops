import { useState, type FormEvent } from "react";

import { ApiError, type ClientData } from "../../lib/api";

type ClientPayload = {
  name: string;
  phone: string | null;
  email: string | null;
  address: string | null;
  notes: string | null;
};

type Props = {
  initial?: ClientData;
  submitLabel: string;
  onSubmit: (payload: ClientPayload) => Promise<void>;
  onCancel?: () => void;
  onReload?: () => void;
};

function optional(form: FormData, name: string): string | null {
  const value = String(form.get(name) ?? "").trim();
  return value || null;
}

export function ClientForm({ initial, submitLabel, onSubmit, onCancel, onReload }: Props) {
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
        phone: optional(form, "phone"),
        email: optional(form, "email"),
        address: optional(form, "address"),
        notes: optional(form, "notes"),
      });
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 412) {
        setConflict(true);
        setError("Este cliente foi alterado em outra sessão. Seus dados foram preservados.");
      } else {
        setError(
          caught instanceof ApiError ? caught.message : "Não foi possível salvar o cliente.",
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
      <label>
        Telefone
        <input name="phone" maxLength={32} defaultValue={initial?.phone ?? ""} />
      </label>
      <label>
        E-mail de contato
        <input name="email" maxLength={254} defaultValue={initial?.email ?? ""} />
      </label>
      <label>
        Endereço
        <textarea name="address" maxLength={500} defaultValue={initial?.address ?? ""} />
      </label>
      <label>
        Notas internas
        <textarea name="notes" maxLength={5000} defaultValue={initial?.notes ?? ""} />
      </label>
      <div className="button-row">
        <button className="button" disabled={saving} type="submit">
          {saving ? "Salvando…" : submitLabel}
        </button>
        {onCancel && (
          <button className="button button--secondary" type="button" onClick={onCancel}>
            Cancelar
          </button>
        )}
      </div>
    </form>
  );
}
