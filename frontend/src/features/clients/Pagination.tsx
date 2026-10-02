type Props = {
  page: { number: number; total_pages: number; total: number };
  onChange: (page: number) => void;
  label: string;
};

export function Pagination({ page, onChange, label }: Props) {
  if (page.total_pages <= 1) return null;
  return (
    <nav className="pagination" aria-label={label}>
      <button
        className="button button--secondary"
        type="button"
        disabled={page.number <= 1}
        onClick={() => onChange(page.number - 1)}
      >
        Anterior
      </button>
      <span>
        Página {page.number} de {page.total_pages} · {page.total} registros
      </span>
      <button
        className="button button--secondary"
        type="button"
        disabled={page.number >= page.total_pages}
        onClick={() => onChange(page.number + 1)}
      >
        Próxima
      </button>
    </nav>
  );
}
