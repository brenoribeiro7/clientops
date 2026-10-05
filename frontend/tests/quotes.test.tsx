import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import { appRoutes, routes } from "../src/app/router";
import { publicClientFromLocation } from "../src/features/quotes/publicClient";
import { ShareDialog } from "../src/features/quotes/ShareDialog";
import { mockSession } from "./auth-fixture";

const bearer = "A".repeat(43);

function renderPath(path: string, configuredRoutes = routes) {
  return render(
    <RouterProvider router={createMemoryRouter(configuredRoutes, { initialEntries: [path] })} />,
  );
}

it("remove o fragmento antes de usar o cliente público e omite credenciais", async () => {
  const replaceState = vi.fn();
  const fetchMock = vi.fn<(input: RequestInfo | URL, options?: RequestInit) => Promise<Response>>(
    async () =>
      new Response(
        JSON.stringify({ data: { status: "APPROVED", approved_at: "2026-10-05T10:00:00Z" } }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
  );
  vi.stubGlobal("fetch", fetchMock);
  const client = publicClientFromLocation(
    { hash: `#token=${bearer}` } as Location,
    { replaceState } as unknown as History,
  );
  expect(replaceState).toHaveBeenCalledWith(null, "", "/q");
  await client?.approve();
  const options = fetchMock.mock.calls[0]?.[1] as RequestInit;
  const headers = new Headers(options.headers);
  expect(options.credentials).toBe("omit");
  expect(headers.get("Authorization")).toBe(`Bearer ${bearer}`);
  expect(localStorage.length).toBe(0);
  expect(sessionStorage.length).toBe(0);
  vi.unstubAllGlobals();
});

it("rejeita fragmentos não canônicos e ainda limpa a URL", () => {
  const replaceState = vi.fn();
  const client = publicClientFromLocation(
    { hash: "#token=abc=" } as Location,
    { replaceState } as unknown as History,
  );
  expect(client).toBeNull();
  expect(replaceState).toHaveBeenCalledWith(null, "", "/q");
});

it("projeta somente o nome do cliente e confirma antes da aprovação", async () => {
  const user = userEvent.setup();
  const publicClient = {
    read: vi.fn().mockResolvedValue({
      business: {
        trade_name: "Oficina Exemplo",
        phone: "71999999999",
        email: "contato@example.com",
        address: "Rua Pública, 1",
        has_logo: false,
      },
      client: { name: "Cliente Público" },
      number: "ORC-000001",
      notes: "Proposta segura",
      valid_until: "2026-10-10",
      items: [
        {
          position: 1,
          description: "Manutenção",
          quantity: "1.000",
          unit_price: "10.00",
          line_total: "10.00",
        },
      ],
      subtotal: "10.00",
      total: "10.00",
      currency: "BRL" as const,
      status: "SENT" as const,
      sent_at: "2026-10-05T10:00:00Z",
      approved_at: null,
      is_expired: false,
      can_approve: true,
      server_now: "2026-10-05T10:00:00Z",
      business_today: "2026-10-05",
    }),
    approve: vi.fn().mockResolvedValue({ status: "APPROVED", approved_at: "2026-10-05T10:01:00Z" }),
  };
  renderPath("/q", appRoutes(publicClient));
  expect(await screen.findByText(/Preparado para Cliente Público/)).toBeInTheDocument();
  expect(document.body.textContent).not.toContain("client-pii-canary");
  await user.click(screen.getByRole("button", { name: "Aprovar orçamento" }));
  expect(publicClient.approve).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Confirmar aprovação" }));
  await waitFor(() => expect(publicClient.approve).toHaveBeenCalledTimes(1));
  expect(await screen.findByText(/Orçamento aprovado em/)).toBeInTheDocument();
});

it("não inclui o link seguro na URL do WhatsApp e limpa ao fechar", async () => {
  const user = userEvent.setup();
  const open = vi.fn();
  const close = vi.fn();
  vi.stubGlobal("open", open);
  render(<ShareDialog shareUrl={`https://example.test/q#token=${bearer}`} onClose={close} />);
  await user.click(screen.getByRole("button", { name: "Abrir WhatsApp" }));
  const whatsappUrl = String(open.mock.calls[0]?.[0]);
  expect(whatsappUrl).toContain("https://wa.me/?text=");
  expect(whatsappUrl).not.toContain(bearer);
  expect(open).toHaveBeenCalledWith(expect.any(String), "_blank", "noopener,noreferrer");
  await user.click(screen.getByRole("button", { name: "Fechar" }));
  expect(close).toHaveBeenCalledTimes(1);
  vi.unstubAllGlobals();
});

it("expõe Orçamentos ao admin e não ao técnico", async () => {
  vi.stubGlobal("fetch", mockSession("ADMIN"));
  const admin = renderPath("/admin");
  expect(await screen.findAllByRole("link", { name: "Orçamentos" })).not.toHaveLength(0);
  admin.unmount();
  vi.stubGlobal("fetch", mockSession("TECHNICIAN"));
  renderPath("/tech/today");
  expect(await screen.findByRole("heading", { name: "Hoje" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Orçamentos" })).not.toBeInTheDocument();
  vi.unstubAllGlobals();
});
