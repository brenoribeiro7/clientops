import { useRef, useState } from "react";

type Props = {
  shareUrl: string | null;
  onClose: () => void;
};

export function ShareDialog({ shareUrl, onClose }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [copyFailed, setCopyFailed] = useState(false);

  if (!shareUrl) return null;

  async function copy() {
    try {
      await navigator.clipboard.writeText(shareUrl ?? "");
      setCopyFailed(false);
    } catch {
      setCopyFailed(true);
      requestAnimationFrame(() => input.current?.select());
    }
  }

  function openWhatsApp() {
    const text = encodeURIComponent(
      "Olá! Preparei um orçamento para você. Vou enviar o link seguro em seguida.",
    );
    window.open(`https://wa.me/?text=${text}`, "_blank", "noopener,noreferrer");
  }

  return (
    <dialog
      className="confirm-dialog"
      open
      aria-labelledby="share-heading"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <div className="confirm-dialog__content">
        <h2 id="share-heading">Compartilhar link seguro</h2>
        <p>O link é exibido uma única vez. Copie-o antes de fechar.</p>
        <label>
          Link do orçamento
          <input ref={input} readOnly value={shareUrl} onFocus={(event) => event.target.select()} />
        </label>
        {copyFailed && (
          <p className="status-message" role="status">
            A cópia automática falhou. Selecione o link acima e copie manualmente.
          </p>
        )}
        <p className="field-help">
          O WhatsApp abre com uma mensagem genérica. Cole o link manualmente na conversa.
        </p>
        <div className="button-row">
          <button className="button" type="button" onClick={() => void copy()}>
            Copiar link
          </button>
          <button className="button button--secondary" type="button" onClick={openWhatsApp}>
            Abrir WhatsApp
          </button>
          <button className="button button--secondary" type="button" onClick={onClose}>
            Fechar
          </button>
        </div>
      </div>
    </dialog>
  );
}
