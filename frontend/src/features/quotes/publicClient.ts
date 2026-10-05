import { ApiError, type PublicApprovalData, type PublicQuoteData } from "../../lib/api";

export type PublicQuoteClient = {
  read: (signal?: AbortSignal) => Promise<PublicQuoteData>;
  approve: () => Promise<PublicApprovalData>;
};

const tokenPattern = /^[A-Za-z0-9_-]{43}$/;

function errorFrom(body: unknown, status: number): ApiError {
  const value = body as { error?: { code?: string; message?: string } } | null;
  return new ApiError(
    status,
    value?.error?.code ?? "REQUEST_FAILED",
    {},
    [],
    "",
    value?.error?.message,
  );
}

export function publicClientFromLocation(
  location: Location,
  history: History,
): PublicQuoteClient | null {
  const fragment = location.hash;
  const raw = fragment.startsWith("#token=") ? fragment.slice(7) : "";
  const valid = tokenPattern.test(raw);
  history.replaceState(null, "", "/q");
  if (!valid) return null;

  async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const headers = new Headers(options.headers);
    headers.set("Accept", "application/json");
    headers.set("Authorization", `Bearer ${raw}`);
    const response = await fetch(`/api/v1${path}`, {
      ...options,
      credentials: "omit",
      headers,
    });
    const body = (await response.json().catch(() => null)) as T | null;
    if (!response.ok) throw errorFrom(body, response.status);
    return body as T;
  }

  return Object.freeze({
    read: async (signal?: AbortSignal) =>
      (await request<{ data: PublicQuoteData }>("/public/quote", { signal })).data,
    approve: async () =>
      (
        await request<{ data: PublicApprovalData }>("/public/quote/approve", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ accept: true }),
        })
      ).data,
  });
}
