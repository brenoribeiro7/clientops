import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import { routes } from "../src/app/router";

function renderPath(path: string) {
  return render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />);
}

describe("shells da Foundation", () => {
  it.each([
    ["/admin", "Fundação administrativa"],
    ["/tech/today", "Fundação do trabalho técnico"],
    ["/q", "Fundação da experiência pública"],
    ["/login", "Acesso ao ClientOps"],
  ])("renderiza %s sem conteúdo comercial fictício", async (path, heading) => {
    renderPath(path);
    expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
    expect(screen.queryByText(/R\$|clientes ativos|faturamento/i)).not.toBeInTheDocument();
  });
});
