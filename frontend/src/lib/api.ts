import type { components } from "../contracts/api";

export type SessionData = components["schemas"]["SessionData"];
export type UserData = components["schemas"]["UserData"];
export type UserPage = components["schemas"]["UserPage"];
export type BusinessProfileData = components["schemas"]["BusinessProfileData"];

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    public readonly details: Record<string, unknown>,
  ) {
    super(code);
  }
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  csrfToken?: string,
): Promise<{ data: T; response: Response }> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (csrfToken) {
    headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { code?: string; details?: Record<string, unknown> };
    } | null;
    throw new ApiError(
      response.status,
      body?.error?.code ?? "REQUEST_FAILED",
      body?.error?.details ?? {},
    );
  }
  const body = response.status === 204 ? undefined : ((await response.json()) as T);
  return { data: body as T, response };
}
