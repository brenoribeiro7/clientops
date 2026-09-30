import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import { routes } from "../src/app/router";

function renderPath(path: string) {
  return render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />);
}

it("redireciona /tech para a rota inicial técnica", async () => {
  renderPath("/tech");
  expect(
    await screen.findByRole("heading", { name: "Fundação do trabalho técnico" }),
  ).toBeInTheDocument();
});

it("mantém página desconhecida no shell administrativo", async () => {
  renderPath("/admin/desconhecida");
  expect(
    await screen.findByRole("navigation", { name: "Navegação administrativa" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Não encontramos este endereço" }),
  ).toBeInTheDocument();
});
