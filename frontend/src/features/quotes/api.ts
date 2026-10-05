import {
  apiRequest,
  type IssuedPublicAccess,
  type QuoteDetail,
  type QuotePage,
  type TimelinePage,
} from "../../lib/api";

export type QuoteListParams = {
  page: number;
  status?: "DRAFT" | "SENT" | "APPROVED" | "CANCELLED";
  q?: string;
  sort: "number" | "-number" | "created_at" | "-created_at" | "valid_until" | "-valid_until";
};

export type QuoteResource = { value: QuoteDetail; etag: string };
export type IssuedQuote = QuoteResource & { publicAccess: IssuedPublicAccess };

export const quoteKeys = {
  all: ["quotes"] as const,
  list: (params: QuoteListParams) => ["quotes", "list", params] as const,
  detail: (id: string) => ["quotes", "detail", id] as const,
  timeline: (id: string) => ["quotes", id, "timeline"] as const,
};

export async function listQuotes(
  params: QuoteListParams,
  signal?: AbortSignal,
): Promise<QuotePage> {
  const search = new URLSearchParams({
    page: String(params.page),
    page_size: "20",
    sort: params.sort,
  });
  if (params.status) search.set("status", params.status);
  if (params.q) search.set("q", params.q);
  return (await apiRequest<QuotePage>(`/quotes?${search}`, { signal })).data;
}

export async function getQuote(id: string, signal?: AbortSignal): Promise<QuoteResource> {
  const result = await apiRequest<{ data: QuoteDetail }>(`/quotes/${id}`, { signal });
  return { value: result.data.data, etag: result.response.headers.get("ETag") ?? "" };
}

async function command<T>(
  path: string,
  body: Record<string, unknown>,
  csrf: string,
  etag?: string,
): Promise<{ data: T; response: Response }> {
  return apiRequest<T>(
    path,
    {
      method: "POST",
      headers: etag ? { "If-Match": etag } : undefined,
      body: JSON.stringify(body),
    },
    csrf,
  );
}

export async function createQuote(
  body: Record<string, unknown>,
  csrf: string,
): Promise<QuoteResource> {
  const result = await command<{ data: QuoteDetail }>("/quotes", body, csrf);
  return { value: result.data.data, etag: result.response.headers.get("ETag") ?? "" };
}

export async function patchQuote(
  id: string,
  body: Record<string, unknown>,
  csrf: string,
  etag: string,
): Promise<QuoteResource> {
  const result = await apiRequest<{ data: QuoteDetail }>(
    `/quotes/${id}`,
    {
      method: "PATCH",
      headers: { "If-Match": etag },
      body: JSON.stringify(body),
    },
    csrf,
  );
  return { value: result.data.data, etag: result.response.headers.get("ETag") ?? "" };
}

export async function sendQuote(id: string, csrf: string, etag: string): Promise<IssuedQuote> {
  const result = await command<{ data: QuoteDetail; public_access: IssuedPublicAccess }>(
    `/quotes/${id}/send`,
    {},
    csrf,
    etag,
  );
  return {
    value: result.data.data,
    publicAccess: result.data.public_access,
    etag: result.response.headers.get("ETag") ?? "",
  };
}

export async function cancelQuote(
  id: string,
  reason: string,
  csrf: string,
  etag: string,
): Promise<QuoteResource> {
  const result = await command<{ data: QuoteDetail }>(
    `/quotes/${id}/cancel`,
    { reason },
    csrf,
    etag,
  );
  return { value: result.data.data, etag: result.response.headers.get("ETag") ?? "" };
}

export async function duplicateQuote(id: string, csrf: string): Promise<QuoteResource> {
  const result = await command<{ data: QuoteDetail }>(`/quotes/${id}/duplicate`, {}, csrf);
  return { value: result.data.data, etag: result.response.headers.get("ETag") ?? "" };
}

export async function rotateQuoteAccess(
  id: string,
  expectedAccessId: string | null,
  csrf: string,
): Promise<IssuedPublicAccess> {
  const result = await command<{ data: IssuedPublicAccess }>(
    `/quotes/${id}/public-access`,
    { expected_access_id: expectedAccessId },
    csrf,
  );
  return result.data.data;
}

export async function revokeQuoteAccess(
  quoteId: string,
  accessId: string,
  csrf: string,
): Promise<void> {
  await command(`/quotes/${quoteId}/public-access/${accessId}/revoke`, {}, csrf);
}

export async function getQuoteTimeline(id: string, signal?: AbortSignal): Promise<TimelinePage> {
  return (await apiRequest<TimelinePage>(`/quotes/${id}/timeline?page=1&page_size=100`, { signal }))
    .data;
}
