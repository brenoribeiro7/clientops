import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";

import { createAppRouter } from "./app/router";
import { publicClientFromLocation } from "./features/quotes/publicClient";
import "./styles/app.css";

const root = document.getElementById("root");
if (!root) {
  throw new Error("Root element is missing");
}

const publicQuoteClient =
  window.location.pathname === "/q"
    ? publicClientFromLocation(window.location, window.history)
    : null;
const router = createAppRouter(publicQuoteClient);

createRoot(root).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
