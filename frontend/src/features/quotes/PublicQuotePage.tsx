import { useEffect, useState } from "react";

import type { PublicQuoteData } from "../../lib/api";
import type { PublicQuoteClient } from "./publicClient";

type Props = { client: PublicQuoteClient | null };
type ViewState =
  { kind: "loading" } | { kind: "unavailable" } | { kind: "ready"; quote: PublicQuoteData };

const unavailableMessage = "Link indisponível. Peça um novo link à empresa.";

function money(value: string) {
  const [whole, decimals] = value.split(".");
  return `R$ ${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ".")},${decimals}`;
}

export default function PublicQuotePage({ client }: Props) {
  const [view, setView] = useState<ViewState>(
    client ? { kind: "loading" } : { kind: "unavailable" },
  );
  const [confirming, setConfirming] = useState(false);
  const [approving, setApproving] = useState(false);

  useEffect(() => {
    if (!client) return;
    const controller = new AbortController();
    client
      .read(controller.signal)
      .then((quote) => setView({ kind: "ready", quote }))
      .catch(() => {
        if (!controller.signal.aborted) setView({ kind: "unavailable" });
      });
    return () => controller.abort();
  }, [client]);

  async function approve() {
    if (!client || view.kind !== "ready") return;
    setApproving(true);
    try {
      const result = await client.approve();
      setView({
        kind: "ready",
        quote: {
          ...view.quote,
          status: "APPROVED",
          approved_at: result.approved_at,
          can_approve: false,
        },
      });
      setConfirming(false);
    } catch {
      setView({ kind: "unavailable" });
    } finally {
      setApproving(false);
    }
  }

  if (view.kind === "loading") {
    return (
      <div className="skeleton" aria-live="polite">
        Carregando orçamento…
      </div>
    );
  }
  if (view.kind === "unavailable") {
    return (
      <section className="empty-state" role="alert">
        <h1>Orçamento indisponível</h1>
        <p>{unavailableMessage}</p>
      </section>
    );
  }

  const { quote } = view;
  return (
    <article className="public-quote">
      <header className="public-quote__heading">
        <div>
          <p className="eyebrow">Orçamento {quote.number}</p>
          <h1>{quote.business.trade_name}</h1>
          <p>Preparado para {quote.client.name}</p>
        </div>
        <span className={`status-badge status-badge--${quote.status.toLowerCase()}`}>
          {quote.status === "APPROVED" ? "Aprovado" : quote.is_expired ? "Vencido" : "Enviado"}
        </span>
      </header>

      <section className="detail-section" aria-labelledby="quote-items-heading">
        <h2 id="quote-items-heading">Itens</h2>
        {/* eslint-disable jsx-a11y/no-noninteractive-tabindex -- keyboard access for the horizontally scrollable table */}
        <div
          className="quote-table-wrap"
          role="region"
          tabIndex={0}
          aria-label="Itens do orçamento"
        >
          <table className="quote-table">
            <thead>
              <tr>
                <th>Descrição</th>
                <th>Qtd.</th>
                <th>Unitário</th>
                <th>Total</th>
              </tr>
            </thead>
            <tbody>
              {quote.items.map((item) => (
                <tr key={`${item.position}-${item.description}`}>
                  <td>{item.description}</td>
                  <td>{item.quantity}</td>
                  <td>{money(item.unit_price)}</td>
                  <td>{money(item.line_total)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <th colSpan={3}>Total</th>
                <td>{money(quote.total)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
        {/* eslint-enable jsx-a11y/no-noninteractive-tabindex */}
      </section>

      <section className="detail-section" aria-labelledby="quote-details-heading">
        <h2 id="quote-details-heading">Detalhes</h2>
        <dl className="details-grid">
          <div>
            <dt>Válido até</dt>
            <dd>{quote.valid_until}</dd>
          </div>
          <div>
            <dt>Observações</dt>
            <dd>{quote.notes ?? "Sem observações"}</dd>
          </div>
        </dl>
      </section>

      {quote.status === "SENT" && quote.is_expired && (
        <p className="status-message status-message--warning" role="status">
          Este orçamento venceu. Entre em contato com a empresa para solicitar uma nova proposta.
        </p>
      )}
      {quote.status === "APPROVED" && quote.approved_at && (
        <p className="status-message status-message--success" role="status">
          Orçamento aprovado em {new Date(quote.approved_at).toLocaleString("pt-BR")}.
        </p>
      )}
      {quote.status === "SENT" && quote.can_approve && !confirming && (
        <button
          className="button public-quote__approve"
          type="button"
          onClick={() => setConfirming(true)}
        >
          Aprovar orçamento
        </button>
      )}
      {confirming && (
        <section className="approval-confirm" aria-labelledby="approval-heading">
          <h2 id="approval-heading">Confirmar aprovação</h2>
          <p>Ao confirmar, este orçamento será registrado como aprovado.</p>
          <div className="button-row">
            <button
              className="button"
              type="button"
              disabled={approving}
              onClick={() => void approve()}
            >
              {approving ? "Confirmando…" : "Confirmar aprovação"}
            </button>
            <button
              className="button button--secondary"
              type="button"
              disabled={approving}
              onClick={() => setConfirming(false)}
            >
              Voltar
            </button>
          </div>
        </section>
      )}

      <footer className="public-quote__contact">
        <h2>Contato</h2>
        <address>
          {quote.business.phone}
          <br />
          {quote.business.email}
          <br />
          {quote.business.address}
        </address>
      </footer>
    </article>
  );
}
