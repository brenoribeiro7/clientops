import { vi } from "vitest";

export function mockSession(role: "ADMIN" | "TECHNICIAN") {
  return vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path.endsWith("/api/v1/auth/session")) {
      return new Response(
        JSON.stringify({
          data: {
            user: {
              id: "00000000-0000-4000-8000-000000000001",
              name: "Test User",
              email: "user@example.com",
              role,
              status: "ACTIVE",
              must_change_password: false,
              version: 1,
            },
            expires_at: "2026-06-01T20:00:00Z",
            idle_expires_at: "2026-06-01T12:30:00Z",
            csrf_token: "csrf-token",
            server_now: "2026-06-01T12:00:00Z",
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    return new Response(JSON.stringify({ error: { code: "NOT_FOUND" } }), { status: 404 });
  });
}
