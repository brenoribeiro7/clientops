import { Menu, X } from "lucide-react";
import { type ReactNode, useRef } from "react";

import { Button } from "./Button";

type DrawerProps = {
  label: string;
  children: ReactNode;
};

export function Drawer({ label, children }: DrawerProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  function open(): void {
    dialogRef.current?.showModal();
  }

  function close(): void {
    dialogRef.current?.close();
  }

  function restoreFocus(): void {
    triggerRef.current?.focus();
  }

  return (
    <div className="drawer">
      <Button ref={triggerRef} variant="secondary" aria-label={label} onClick={open}>
        <Menu aria-hidden="true" size={20} />
        Menu
      </Button>
      <dialog ref={dialogRef} className="drawer__dialog" onClose={restoreFocus}>
        <div className="drawer__panel">
          <Button variant="secondary" aria-label="Fechar menu" onClick={close}>
            <X aria-hidden="true" size={20} />
            Fechar
          </Button>
          {children}
        </div>
      </dialog>
    </div>
  );
}
