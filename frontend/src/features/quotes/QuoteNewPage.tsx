import { useNavigate } from "react-router-dom";

import { useAuth } from "../../app/auth/AuthProvider";
import { createQuote } from "./api";
import { QuoteEditor } from "./QuoteEditor";

export default function QuoteNewPage() {
  const { session } = useAuth();
  const navigate = useNavigate();

  async function create(payload: Record<string, unknown>) {
    if (!session) return;
    const result = await createQuote(payload, session.csrf_token);
    navigate(`/admin/quotes/${result.value.id}`);
  }

  return (
    <section className="quotes-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Orçamentos</p>
          <h1>Novo orçamento</h1>
          <p className="foundation-description">Salve o rascunho antes de enviá-lo ao cliente.</p>
        </div>
      </div>
      <QuoteEditor submitLabel="Criar rascunho" onSubmit={create} />
    </section>
  );
}
