import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import { routes } from "../src/app/router";
import { mockSession } from "./auth-fixture";

function renderPath(path: string) {
  return render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />);
}

describe("shells da Foundation", () => {
  it.each([
    ["/admin", "Visão administrativa", "ADMIN"],
    ["/tech/today", "Hoje", "TECHNICIAN"],
  ] as const)("renderiza %s sem conteúdo comercial fictício", async (path, heading, role) => {
    vi.stubGlobal("fetch", mockSession(role));
    renderPath(path);
    expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
    expect(screen.queryByText(/R\$|clientes ativos|faturamento/i)).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it.each([
    ["/q", "Orçamento indisponível"],
    ["/login", "Entrar no ClientOps"],
  ])("renderiza %s sem conteúdo comercial fictício", async (path, heading) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("", { status: 401 })),
    );
    renderPath(path);
    expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
    expect(screen.queryByText(/R\$|clientes ativos|faturamento/i)).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
