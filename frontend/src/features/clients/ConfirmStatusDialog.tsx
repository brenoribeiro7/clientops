import { useRef } from "react";

type Props = {
  action: string;
  description: string;
  onConfirm: () => void;
};

export function ConfirmStatusDialog({ action, description, onConfirm }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  return (
    <>
      <button
        ref={trigger}
        className="button button--secondary"
        type="button"
        onClick={() => dialog.current?.showModal()}
      >
        {action}
      </button>
      <dialog ref={dialog} className="confirm-dialog" onClose={() => trigger.current?.focus()}>
        <form method="dialog" className="confirm-dialog__content">
          <h2>Confirmar {action.toLowerCase()}</h2>
          <p>{description}</p>
          <div className="button-row">
            <button className="button button--secondary" value="cancel">
              Cancelar
            </button>
            <button
              className="button"
              value="confirm"
              onClick={() => {
                onConfirm();
              }}
            >
              {action}
            </button>
          </div>
        </form>
      </dialog>
    </>
  );
}
