import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate, type RouteObject } from "react-router-dom";

import { FoundationPage } from "./pages/FoundationPage";
import { LoginShell } from "./pages/LoginShell";
import { NotFoundPage } from "./pages/NotFoundPage";

const AdminLayout = lazy(() =>
  import("./layouts/AdminLayout").then((module) => ({ default: module.AdminLayout })),
);
const TechnicianLayout = lazy(() =>
  import("./layouts/TechnicianLayout").then((module) => ({ default: module.TechnicianLayout })),
);
const PublicLayout = lazy(() =>
  import("./layouts/PublicLayout").then((module) => ({ default: module.PublicLayout })),
);

function LoadingRoute() {
  return (
    <main id="main-content" className="route-loading" aria-live="polite">
      Carregando estrutura…
    </main>
  );
}

function lazyElement(element: React.ReactNode) {
  return <Suspense fallback={<LoadingRoute />}>{element}</Suspense>;
}

export const routes: RouteObject[] = [
  {
    path: "/admin",
    element: lazyElement(<AdminLayout />),
    children: [
      {
        index: true,
        element: (
          <FoundationPage
            eyebrow="Área administrativa"
            title="Fundação administrativa"
            description="A estrutura de navegação está pronta para receber os módulos das próximas fases."
          />
        ),
      },
      { path: "*", element: <NotFoundPage home="/admin" /> },
    ],
  },
  {
    path: "/tech",
    element: lazyElement(<TechnicianLayout />),
    children: [
      { index: true, element: <Navigate to="today" replace /> },
      {
        path: "today",
        element: (
          <FoundationPage
            eyebrow="Área técnica"
            title="Fundação do trabalho técnico"
            description="A área está preparada para a jornada operacional das próximas fases."
          />
        ),
      },
      { path: "*", element: <NotFoundPage home="/tech/today" /> },
    ],
  },
  {
    path: "/q",
    element: lazyElement(<PublicLayout />),
    children: [
      {
        index: true,
        element: (
          <FoundationPage
            eyebrow="Área pública"
            title="Fundação da experiência pública"
            description="Este endereço receberá propostas compartilhadas em uma fase posterior."
          />
        ),
      },
      { path: "*", element: <NotFoundPage home="/q" /> },
    ],
  },
  { path: "/login", element: <LoginShell /> },
  { path: "/", element: <Navigate to="/login" replace /> },
  { path: "*", element: <NotFoundPage home="/login" /> },
];

export const router = createBrowserRouter(routes);
