import type { components } from "../contracts/api";

export type SessionData = components["schemas"]["SessionData"];
export type UserData = components["schemas"]["UserData"];
export type UserPage = components["schemas"]["UserPage"];
export type BusinessProfileData = components["schemas"]["BusinessProfileData"];
export type ClientData = components["schemas"]["ClientData"];
export type ClientPage = components["schemas"]["ClientPage"];
export type EquipmentData = components["schemas"]["EquipmentData"];
export type EquipmentPage = components["schemas"]["EquipmentPage"];
export type TimelinePage = components["schemas"]["TimelinePage"];

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    public readonly details: Record<string, unknown>,
    public readonly fields: Array<{ field: string; message: string }> = [],
    public readonly requestId = "",
    message = code,
  ) {
    super(message);
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
      error?: {
        code?: string;
        message?: string;
        details?: Record<string, unknown>;
        fields?: Array<{ field: string; message: string }>;
        request_id?: string;
      };
    } | null;
    throw new ApiError(
      response.status,
      body?.error?.code ?? "REQUEST_FAILED",
      body?.error?.details ?? {},
      body?.error?.fields ?? [],
      body?.error?.request_id ?? "",
      body?.error?.message,
    );
  }
  const body = response.status === 204 ? undefined : ((await response.json()) as T);
  return { data: body as T, response };
}
