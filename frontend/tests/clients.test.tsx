import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import { routes } from "../src/app/router";
import { ClientForm } from "../src/features/clients/ClientForm";
import { ApiError } from "../src/lib/api";
import { mockSession } from "./auth-fixture";

function renderPath(path: string) {
  return render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />);
}

it("mostra o estado vazio e a ação principal de clientes", async () => {
  const session = mockSession("ADMIN");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).includes("/api/v1/clients?")) {
        return new Response(
          JSON.stringify({
            data: [],
            page: { number: 1, size: 20, total: 0, total_pages: 0 },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return session(input);
    }),
  );
  renderPath("/admin/clients");
  expect(await screen.findByRole("heading", { level: 1, name: "Clientes" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Cadastrar cliente" })).toBeInTheDocument();
  expect(
    await screen.findByRole("heading", { name: "Nenhum cliente neste status" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Clientes" })).toHaveAttribute("href", "/admin/clients");
  vi.unstubAllGlobals();
});

it("renderiza detalhe, equipamento e timeline sem interpretar payload como HTML", async () => {
  const session = mockSession("ADMIN");
  const clientId = "00000000-0000-4000-8000-0000000000c3";
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith(`/api/v1/clients/${clientId}`)) {
        return new Response(
          JSON.stringify({
            data: {
              id: clientId,
              name: "Cliente Teste",
              phone: null,
              email: null,
              address: null,
              notes: null,
              status: "ACTIVE",
              archived_at: null,
              created_at: "2026-10-02T15:00:00Z",
              updated_at: "2026-10-02T15:00:00Z",
              version: 1,
              links: { equipment: "equipment", timeline: "timeline" },
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json", ETag: '"v1"' } },
        );
      }
      if (path.includes(`/api/v1/clients/${clientId}/equipment?`)) {
        return new Response(
          JSON.stringify({
            data: [],
            page: { number: 1, size: 20, total: 0, total_pages: 0 },
          }),
          { status: 200 },
        );
      }
      if (path.includes(`/api/v1/clients/${clientId}/timeline?`)) {
        return new Response(
          JSON.stringify({
            data: [
              {
                id: "00000000-0000-4000-8000-0000000000e3",
                event_type: "client.created",
                occurred_at: "2026-10-02T15:00:00Z",
                actor: { type: "USER", display_name: "Admin" },
                payload: { changed_fields: ["<script>alert(1)</script>"] },
              },
            ],
            page: { number: 1, size: 20, total: 1, total_pages: 1 },
          }),
          { status: 200 },
        );
      }
      return session(input);
    }),
  );
  renderPath(`/admin/clients/${clientId}`);
  expect(
    await screen.findByRole("heading", { level: 1, name: "Cliente Teste" }),
  ).toBeInTheDocument();
  expect(await screen.findByRole("heading", { name: "Equipamentos" })).toBeInTheDocument();
  expect(await screen.findByText("client.created")).toBeInTheDocument();
  expect(document.querySelector("script")).toBeNull();
  vi.unstubAllGlobals();
});

it("não apresenta navegação Clientes ao técnico", async () => {
  vi.stubGlobal("fetch", mockSession("TECHNICIAN"));
  renderPath("/admin/clients");
  expect(await screen.findByRole("heading", { name: "Hoje" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Clientes" })).not.toBeInTheDocument();
  vi.unstubAllGlobals();
});

it("preserva o formulário e exige recarga explícita após conflito 412", async () => {
  const user = userEvent.setup();
  const submit = vi
    .fn()
    .mockRejectedValue(
      new ApiError(
        412,
        "VERSION_CONFLICT",
        { current_version: 2 },
        [],
        "00000000-0000-4000-8000-000000000412",
        "Versão desatualizada.",
      ),
    );
  const reload = vi.fn();
  render(
    <ClientForm
      initial={{
        id: "00000000-0000-4000-8000-0000000000c3",
        name: "Nome original",
        phone: null,
        email: null,
        address: null,
        notes: null,
        status: "ACTIVE",
        archived_at: null,
        created_at: "2026-10-02T15:00:00Z",
        updated_at: "2026-10-02T15:00:00Z",
        version: 1,
        links: { equipment: "equipment", timeline: "timeline" },
      }}
      submitLabel="Salvar cliente"
      onSubmit={submit}
      onReload={reload}
    />,
  );
  const name = screen.getByLabelText("Nome", { exact: true });
  await user.clear(name);
  await user.type(name, "Minha edição local");
  await user.click(screen.getByRole("button", { name: "Salvar cliente" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Este cliente foi alterado em outra sessão. Seus dados foram preservados.",
  );
  expect(name).toHaveValue("Minha edição local");
  expect(submit).toHaveBeenCalledTimes(1);
  expect(reload).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Recarregar versão atual" }));
  expect(reload).toHaveBeenCalledTimes(1);
});
