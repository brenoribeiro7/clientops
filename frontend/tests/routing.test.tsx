import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import { routes } from "../src/app/router";
import { mockSession } from "./auth-fixture";

function renderPath(path: string) {
  return render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />);
}

it("redireciona /tech para a rota inicial técnica", async () => {
  vi.stubGlobal("fetch", mockSession("TECHNICIAN"));
  renderPath("/tech");
  expect(await screen.findByRole("heading", { name: "Hoje" })).toBeInTheDocument();
  vi.unstubAllGlobals();
});

it("mantém página desconhecida no shell administrativo", async () => {
  vi.stubGlobal("fetch", mockSession("ADMIN"));
  renderPath("/admin/desconhecida");
  expect(
    await screen.findByRole("navigation", { name: "Navegação administrativa" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Não encontramos este endereço" }),
  ).toBeInTheDocument();
  vi.unstubAllGlobals();
});

it("mantém /q fora da infraestrutura privada de autenticação", async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  renderPath("/q");
  expect(
    await screen.findByRole("heading", { name: "Orçamento indisponível" }),
  ).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
  vi.unstubAllGlobals();
});

it("remove a sessão da árvore React imediatamente ao sair", async () => {
  const sessionFetch = mockSession("ADMIN");
  let loggedOut = false;
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    if (String(input).endsWith("/api/v1/auth/logout")) {
      loggedOut = true;
      return new Response(null, { status: 204 });
    }
    if (loggedOut && String(input).endsWith("/api/v1/auth/session")) {
      return new Response(JSON.stringify({ error: { code: "AUTHENTICATION_REQUIRED" } }), {
        status: 401,
      });
    }
    return sessionFetch(input);
  });
  vi.stubGlobal("fetch", fetchMock);
  renderPath("/admin/account");
  expect(await screen.findByRole("heading", { name: "Test User" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Sair" }));
  await waitFor(() => {
    expect(screen.getByRole("heading", { name: "Entrar no ClientOps" })).toBeInTheDocument();
  });
  expect(screen.queryByRole("heading", { name: "Test User" })).not.toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/auth/logout",
    expect.objectContaining({ method: "POST" }),
  );
  vi.unstubAllGlobals();
});
