import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { useAuth } from "../../app/auth/AuthProvider";
import type { ApiError, QuoteDetail } from "../../lib/api";
import {
  cancelQuote,
  duplicateQuote,
  getQuote,
  getQuoteTimeline,
  patchQuote,
  quoteKeys,
  revokeQuoteAccess,
  rotateQuoteAccess,
  sendQuote,
} from "./api";
import { QuoteEditor } from "./QuoteEditor";
import { ShareDialog } from "./ShareDialog";

function money(value: string) {
  const [whole, decimals] = value.split(".");
  return `R$ ${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ".")},${decimals}`;
}

function snapshotName(quote: QuoteDetail): string | null {
  const client = quote.commercial_snapshot?.client;
  if (typeof client !== "object" || client === null || !("name" in client)) return null;
  return typeof client.name === "string" ? client.name : null;
}

export default function QuoteDetailPage() {
  const { quoteId = "" } = useParams();
  const { session } = useAuth();
  const navigate = useNavigate();
  const cache = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [confirmingSend, setConfirmingSend] = useState(false);
  const [sending, setSending] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const quoteQuery = useQuery({
    queryKey: quoteKeys.detail(quoteId),
    queryFn: ({ signal }) => getQuote(quoteId, signal),
  });
  const timeline = useQuery({
    queryKey: quoteKeys.timeline(quoteId),
    queryFn: ({ signal }) => getQuoteTimeline(quoteId, signal),
  });

  async function refresh() {
    await Promise.all([
      cache.invalidateQueries({ queryKey: quoteKeys.detail(quoteId) }),
      cache.invalidateQueries({ queryKey: quoteKeys.timeline(quoteId) }),
      cache.invalidateQueries({ queryKey: quoteKeys.all }),
    ]);
  }

  async function save(payload: Record<string, unknown>) {
    if (!session || !quoteQuery.data) return;
    await patchQuote(quoteId, payload, session.csrf_token, quoteQuery.data.etag);
    setEditing(false);
    setMessage("Orçamento salvo.");
    await refresh();
  }

  async function send() {
    if (!session || !quoteQuery.data) return;
    setSending(true);
    setMessage("");
    try {
      const result = await sendQuote(quoteId, session.csrf_token, quoteQuery.data.etag);
      setConfirmingSend(false);
      setShareUrl(result.publicAccess.share_url);
      setMessage("Orçamento enviado. Copie o link seguro agora.");
      await refresh();
    } catch {
      setMessage("Não foi possível enviar. Recarregue e revise o orçamento.");
    } finally {
      setSending(false);
    }
  }

  async function cancel(event: FormEvent) {
    event.preventDefault();
    if (!session || !quoteQuery.data) return;
    try {
      await cancelQuote(quoteId, cancelReason, session.csrf_token, quoteQuery.data.etag);
      setCancelReason("");
      setMessage("Orçamento cancelado.");
      await refresh();
    } catch {
      setMessage("Não foi possível cancelar. Recarregue a página.");
    }
  }

  async function duplicate() {
    if (!session) return;
    try {
      const result = await duplicateQuote(quoteId, session.csrf_token);
      navigate(`/admin/quotes/${result.value.id}`);
    } catch {
      setMessage("Não foi possível duplicar o orçamento.");
    }
  }

  async function rotate() {
    if (!session || !quoteQuery.data) return;
    try {
      const access = await rotateQuoteAccess(
        quoteId,
        quoteQuery.data.value.public_access?.id ?? null,
        session.csrf_token,
      );
      setShareUrl(access.share_url);
      setMessage("Novo link emitido. O link anterior deixou de funcionar.");
      await refresh();
    } catch (caught) {
      const changed = (caught as ApiError).code === "ACCESS_CHANGED";
      setMessage(
        changed
          ? "O acesso mudou em outra sessão. Recarregue a página."
          : "Não foi possível gerar um novo link.",
      );
    }
  }

  async function revoke() {
    const accessId = quoteQuery.data?.value.public_access?.id;
    if (!session || !accessId) return;
    try {
      await revokeQuoteAccess(quoteId, accessId, session.csrf_token);
      setMessage("Acesso público revogado.");
      await refresh();
    } catch {
      setMessage("Não foi possível revogar o acesso.");
    }
  }

  if (quoteQuery.isPending)
    return (
      <div className="skeleton" aria-live="polite">
        Carregando orçamento…
      </div>
    );
  if (quoteQuery.isError || !quoteQuery.data) {
    return (
      <section className="empty-state" role="alert">
        <h1>Não foi possível carregar o orçamento</h1>
        <button className="button button--secondary" onClick={() => void quoteQuery.refetch()}>
          Tentar novamente
        </button>
      </section>
    );
  }

  const quote = quoteQuery.data.value;
  const editable = quote.status === "DRAFT";
  return (
    <div className="quote-detail">
      <Link className="back-link" to="/admin/quotes">
        ← Voltar para orçamentos
      </Link>
      <header className="detail-header">
        <div>
          <p className="eyebrow">Orçamento</p>
          <h1>{quote.number}</h1>
          <span className={`status-badge status-badge--${quote.status.toLowerCase()}`}>
            {quote.is_expired ? "Vencido" : quote.status}
          </span>
        </div>
        <div className="button-row">
          {editable && (
            <button
              className="button button--secondary"
              type="button"
              onClick={() => setEditing(true)}
            >
              Editar
            </button>
          )}
          <button
            className="button button--secondary"
            type="button"
            onClick={() => void duplicate()}
          >
            Duplicar
          </button>
          {quote.status === "SENT" && !quote.is_expired && (
            <button
              className="button button--secondary"
              type="button"
              onClick={() => void rotate()}
            >
              Gerar novo link
            </button>
          )}
          {quote.public_access && !quote.public_access.revoked_at && (
            <button
              className="button button--secondary"
              type="button"
              onClick={() => void revoke()}
            >
              Revogar acesso
            </button>
          )}
        </div>
      </header>

      {message && (
        <p className="status-message" role="status">
          {message}
        </p>
      )}
      {editing && editable ? (
        <section aria-labelledby="edit-quote-heading">
          <h2 id="edit-quote-heading">Editar rascunho</h2>
          <QuoteEditor
            key={quoteQuery.data.etag}
            initial={quote}
            submitLabel="Salvar orçamento"
            onSubmit={save}
            onCancel={() => setEditing(false)}
            onReload={() => void quoteQuery.refetch()}
          />
        </section>
      ) : (
        <>
          <section className="detail-section" aria-labelledby="commercial-heading">
            <h2 id="commercial-heading">Proposta comercial</h2>
            <dl className="details-grid">
              {snapshotName(quote) && (
                <div>
                  <dt>Cliente na emissão</dt>
                  <dd>{snapshotName(quote)}</dd>
                </div>
              )}
              <div>
                <dt>Validade</dt>
                <dd>{quote.valid_until}</dd>
              </div>
              <div>
                <dt>Subtotal</dt>
                <dd>{money(quote.subtotal)}</dd>
              </div>
              <div>
                <dt>Total</dt>
                <dd>
                  <strong>{money(quote.total)}</strong>
                </dd>
              </div>
              <div>
                <dt>Observações</dt>
                <dd>{quote.notes ?? "Sem observações"}</dd>
              </div>
            </dl>
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
                    <th>Item</th>
                    <th>Qtd.</th>
                    <th>Unitário</th>
                    <th>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {quote.items.map((item) => (
                    <tr key={item.id}>
                      <td>{item.description}</td>
                      <td>{item.quantity}</td>
                      <td>{money(item.unit_price)}</td>
                      <td>{money(item.line_total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {/* eslint-enable jsx-a11y/no-noninteractive-tabindex */}
          </section>

          {editable && (
            <section className="detail-section action-panel" aria-labelledby="send-heading">
              <h2 id="send-heading">Enviar ao cliente</h2>
              <p>Depois do envio, os dados comerciais ficam somente para leitura.</p>
              {!confirmingSend ? (
                <button
                  className="button"
                  type="button"
                  disabled={quote.items.length === 0}
                  onClick={() => setConfirmingSend(true)}
                >
                  Enviar orçamento
                </button>
              ) : (
                <div className="approval-confirm">
                  <strong>Confirma o envio deste orçamento?</strong>
                  <div className="button-row">
                    <button
                      className="button"
                      type="button"
                      disabled={sending}
                      onClick={() => void send()}
                    >
                      {sending ? "Enviando…" : "Confirmar e enviar"}
                    </button>
                    <button
                      className="button button--secondary"
                      type="button"
                      disabled={sending}
                      onClick={() => setConfirmingSend(false)}
                    >
                      Voltar
                    </button>
                  </div>
                </div>
              )}
            </section>
          )}

          {(quote.status === "DRAFT" || quote.status === "SENT") && (
            <section className="detail-section action-panel" aria-labelledby="cancel-heading">
              <h2 id="cancel-heading">Cancelar orçamento</h2>
              <form className="inline-action" onSubmit={(event) => void cancel(event)}>
                <label>
                  Motivo do cancelamento
                  <input
                    required
                    maxLength={1000}
                    value={cancelReason}
                    onChange={(event) => setCancelReason(event.target.value)}
                  />
                </label>
                <button className="button button--secondary" type="submit">
                  Cancelar orçamento
                </button>
              </form>
            </section>
          )}
        </>
      )}

      <section className="detail-section" aria-labelledby="quote-timeline-heading">
        <h2 id="quote-timeline-heading">Histórico</h2>
        {timeline.isPending && <p aria-live="polite">Carregando histórico…</p>}
        {timeline.isError && <p role="alert">Não foi possível carregar o histórico.</p>}
        <ol className="timeline-list">
          {timeline.data?.data.map((event) => (
            <li key={event.id}>
              <strong>{event.event_type}</strong>
              <span>{new Date(event.occurred_at).toLocaleString("pt-BR")}</span>
              <span>por {event.actor.display_name}</span>
            </li>
          ))}
        </ol>
      </section>
      <ShareDialog shareUrl={shareUrl} onClose={() => setShareUrl(null)} />
    </div>
  );
}
