import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { apiRequest, ApiError, type SessionData } from "../../lib/api";

type AuthValue = {
  session: SessionData | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<SessionData>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<SessionData>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthValue | null>(null);
const sessionKey = ["private-session"] as const;

function AuthState({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: sessionKey,
    queryFn: async () => {
      try {
        const result = await apiRequest<{ data: SessionData }>("/auth/session");
        return result.data.data;
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    retry: false,
    staleTime: 30_000,
  });
  const session = query.data ?? null;
  const value = useMemo<AuthValue>(
    () => ({
      session,
      loading: query.isPending,
      login: async (email, password) => {
        const result = await apiRequest<{ data: SessionData }>("/auth/login", {
          method: "POST",
          headers: { "X-ClientOps-Request": "browser-v1" },
          body: JSON.stringify({ email, password }),
        });
        queryClient.setQueryData(sessionKey, result.data.data);
        return result.data.data;
      },
      changePassword: async (currentPassword, newPassword) => {
        if (!session) throw new ApiError(401, "AUTHENTICATION_REQUIRED", {});
        const result = await apiRequest<{ data: SessionData }>(
          "/auth/change-password",
          {
            method: "POST",
            body: JSON.stringify({
              current_password: currentPassword,
              new_password: newPassword,
            }),
          },
          session.csrf_token,
        );
        queryClient.setQueryData(sessionKey, result.data.data);
        return result.data.data;
      },
      logout: async () => {
        try {
          await apiRequest<void>(
            "/auth/logout",
            {
              method: "POST",
              headers: { "X-ClientOps-Request": "browser-v1" },
              body: JSON.stringify({}),
            },
            session?.csrf_token,
          );
        } finally {
          queryClient.removeQueries({
            predicate: (query) => query.queryKey[0] !== sessionKey[0],
          });
          queryClient.setQueryData(sessionKey, null);
        }
      },
    }),
    [query.isPending, queryClient, session],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function AuthInfrastructure() {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: false },
          mutations: { retry: false },
        },
      }),
  );
  return (
    <QueryClientProvider client={queryClient}>
      <AuthState>
        <Outlet />
      </AuthState>
    </QueryClientProvider>
  );
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("AuthProvider is not mounted");
  return value;
}

export function RequireAuth() {
  const { session, loading } = useAuth();
  const location = useLocation();
  if (loading) return <main id="main-content">Carregando sessão…</main>;
  if (!session) return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  if (session.user.must_change_password && location.pathname !== "/change-password") {
    return <Navigate to="/change-password" replace />;
  }
  return <Outlet />;
}

export function RequireRole({ requiredRole }: { requiredRole: "ADMIN" | "TECHNICIAN" }) {
  const { session } = useAuth();
  if (!session) return <Navigate to="/login" replace />;
  if (session.user.role !== requiredRole) {
    return <Navigate to={session.user.role === "ADMIN" ? "/admin" : "/tech/today"} replace />;
  }
  return <Outlet />;
}
