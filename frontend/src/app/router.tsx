import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate, type RouteObject } from "react-router-dom";

import { FoundationPage } from "./pages/FoundationPage";
import { AccountPage } from "./pages/AccountPage";
import { BusinessSettingsPage } from "./pages/BusinessSettingsPage";
import { ChangePasswordPage } from "./pages/ChangePasswordPage";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { UsersPage } from "./pages/UsersPage";
import { AuthInfrastructure, RequireAuth, RequireRole } from "./auth/AuthProvider";
import type { PublicQuoteClient } from "../features/quotes/publicClient";

const AdminLayout = lazy(() =>
  import("./layouts/AdminLayout").then((module) => ({ default: module.AdminLayout })),
);
const TechnicianLayout = lazy(() =>
  import("./layouts/TechnicianLayout").then((module) => ({ default: module.TechnicianLayout })),
);
const PublicLayout = lazy(() =>
  import("./layouts/PublicLayout").then((module) => ({ default: module.PublicLayout })),
);
const ClientListPage = lazy(() => import("../features/clients/ClientListPage"));
const ClientDetailPage = lazy(() => import("../features/clients/ClientDetailPage"));
const QuoteListPage = lazy(() => import("../features/quotes/QuoteListPage"));
const QuoteNewPage = lazy(() => import("../features/quotes/QuoteNewPage"));
const QuoteDetailPage = lazy(() => import("../features/quotes/QuoteDetailPage"));
const PublicQuotePage = lazy(() => import("../features/quotes/PublicQuotePage"));

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

export function appRoutes(publicQuoteClient: PublicQuoteClient | null): RouteObject[] {
  return [
    {
      element: <AuthInfrastructure />,
      children: [
        {
          path: "/login",
          element: <LoginPage />,
        },
        {
          path: "/change-password",
          element: <ChangePasswordPage />,
        },
        {
          element: <RequireAuth />,
          children: [
            {
              element: <RequireRole requiredRole="ADMIN" />,
              children: [
                {
                  path: "/admin",
                  element: lazyElement(<AdminLayout />),
                  children: [
                    {
                      index: true,
                      element: (
                        <FoundationPage
                          eyebrow="Área administrativa"
                          title="Visão administrativa"
                          description="Gerencie a empresa, os usuários e sua conta."
                        />
                      ),
                    },
                    { path: "account", element: <AccountPage /> },
                    { path: "settings", element: <BusinessSettingsPage /> },
                    { path: "settings/users", element: <UsersPage /> },
                    { path: "clients", element: lazyElement(<ClientListPage />) },
                    { path: "clients/:clientId", element: lazyElement(<ClientDetailPage />) },
                    { path: "quotes", element: lazyElement(<QuoteListPage />) },
                    { path: "quotes/new", element: lazyElement(<QuoteNewPage />) },
                    { path: "quotes/:quoteId", element: lazyElement(<QuoteDetailPage />) },
                    { path: "*", element: <NotFoundPage home="/admin" /> },
                  ],
                },
              ],
            },
            {
              element: <RequireRole requiredRole="TECHNICIAN" />,
              children: [
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
                          title="Hoje"
                          description="Sua agenda operacional será adicionada na CL-05."
                        />
                      ),
                    },
                    { path: "account", element: <AccountPage /> },
                    { path: "*", element: <NotFoundPage home="/tech/today" /> },
                  ],
                },
              ],
            },
          ],
        },
      ],
    },
    {
      path: "/q",
      element: lazyElement(<PublicLayout />),
      children: [
        {
          index: true,
          element: lazyElement(<PublicQuotePage client={publicQuoteClient} />),
        },
        { path: "*", element: <NotFoundPage home="/q" /> },
      ],
    },
    { path: "/", element: <Navigate to="/login" replace /> },
    { path: "*", element: <NotFoundPage home="/login" /> },
  ];
}

export function createAppRouter(publicQuoteClient: PublicQuoteClient | null) {
  return createBrowserRouter(appRoutes(publicQuoteClient));
}

export const routes = appRoutes(null);
