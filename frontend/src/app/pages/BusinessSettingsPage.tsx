import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { apiRequest, type BusinessProfileData } from "../../lib/api";
import { useAuth } from "../auth/AuthProvider";

type ProfileState = { profile: BusinessProfileData; etag: string };

export function BusinessSettingsPage() {
  const { session } = useAuth();
  const queryClient = useQueryClient();
  const [message, setMessage] = useState("");
  const query = useQuery({
    queryKey: ["business-profile"],
    queryFn: async (): Promise<ProfileState> => {
      const result = await apiRequest<{ data: BusinessProfileData }>("/business-profile");
      return { profile: result.data.data, etag: result.response.headers.get("ETag") ?? "" };
    },
  });
  if (query.isPending) return <p>Carregando empresa…</p>;
  if (!query.data || query.isError) return <p role="alert">Não foi possível carregar a empresa.</p>;
  const { profile, etag } = query.data;
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session) return;
    const form = new FormData(event.currentTarget);
    const nextTimezone = String(form.get("timezone"));
    const payload = {
      trade_name: String(form.get("tradeName")) || null,
      phone: String(form.get("phone")) || null,
      email: String(form.get("email")) || null,
      address: String(form.get("address")) || null,
      timezone: nextTimezone || null,
      acknowledge_timezone_change: Boolean(profile.timezone) && nextTimezone !== profile.timezone,
    };
    try {
      await apiRequest(
        "/business-profile",
        { method: "PATCH", headers: { "If-Match": etag }, body: JSON.stringify(payload) },
        session.csrf_token,
      );
      await queryClient.invalidateQueries({ queryKey: ["business-profile"] });
      setMessage("Dados salvos.");
    } catch {
      setMessage("Não foi possível salvar. Recarregue e tente novamente.");
    }
  }
  return (
    <section>
      <p className="eyebrow">Configurações</p>
      <h1>Dados da empresa</h1>
      <p>
        {profile.is_complete
          ? "Cadastro completo."
          : `Pendências: ${profile.missing_fields.join(", ")}.`}
      </p>
      {profile.business_today && <p>Data local da empresa: {profile.business_today}</p>}
      <form className="form-card form-card--wide" onSubmit={submit}>
        <label>
          Nome comercial
          <input name="tradeName" defaultValue={profile.trade_name ?? ""} />
        </label>
        <label>
          Telefone
          <input name="phone" defaultValue={profile.phone ?? ""} />
        </label>
        <label>
          E-mail de contato
          <input name="email" type="email" defaultValue={profile.email ?? ""} />
        </label>
        <label>
          Endereço
          <textarea name="address" defaultValue={profile.address ?? ""} />
        </label>
        <label>
          Timezone IANA
          <input
            name="timezone"
            placeholder="Ex.: America/Bahia"
            defaultValue={profile.timezone ?? ""}
          />
        </label>
        {!profile.timezone && (
          <p className="field-help">Escolha explicitamente; o navegador não define esse valor.</p>
        )}
        {message && <p role="status">{message}</p>}
        <button className="button" type="submit">
          Salvar
        </button>
      </form>
    </section>
  );
}
