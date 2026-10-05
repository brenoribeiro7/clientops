export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`status-badge status-badge--${status.toLowerCase()}`}>
      {status === "ACTIVE" ? "Ativo" : "Arquivado"}
    </span>
  );
}
