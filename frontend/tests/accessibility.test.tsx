import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import { routes } from "../src/app/router";

it("oferece skip link e drawer operável por teclado", async () => {
  const user = userEvent.setup();
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ["/admin"] })} />);

  const skip = await screen.findByRole("link", { name: "Ir para o conteúdo" });
  expect(skip).toHaveAttribute("href", "#main-content");

  const trigger = screen.getByRole("button", { name: "Abrir menu administrativo" });
  await user.click(trigger);
  const dialog = screen.getByRole("dialog");
  expect(dialog).toHaveAttribute("open");

  await user.click(screen.getByRole("button", { name: "Fechar menu" }));
  expect(dialog).not.toHaveAttribute("open");
  expect(trigger).toHaveFocus();
});
