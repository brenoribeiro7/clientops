import {
  apiRequest,
  type ClientData,
  type ClientPage,
  type EquipmentData,
  type EquipmentPage,
  type TimelinePage,
} from "../../lib/api";

export type ListParams = {
  page: number;
  pageSize: number;
  status: "ACTIVE" | "ARCHIVED";
  q?: string;
  sort: "name" | "-name" | "created_at" | "-created_at";
};

export type Resource<T> = { value: T; etag: string };

export const clientKeys = {
  all: ["clients"] as const,
  list: (params: ListParams) => ["clients", "list", params] as const,
  detail: (clientId: string) => ["clients", "detail", clientId] as const,
  equipment: (clientId: string, params: ListParams) =>
    ["clients", clientId, "equipment", "list", params] as const,
  timeline: (clientId: string, page: number) => ["clients", clientId, "timeline", page] as const,
};

function query(params: ListParams): string {
  const search = new URLSearchParams({
    page: String(params.page),
    page_size: String(params.pageSize),
    status: params.status,
    sort: params.sort,
  });
  if (params.q) search.set("q", params.q);
  return search.toString();
}

export async function listClients(params: ListParams, signal?: AbortSignal): Promise<ClientPage> {
  return (await apiRequest<ClientPage>(`/clients?${query(params)}`, { signal })).data;
}

export async function getClient(
  clientId: string,
  signal?: AbortSignal,
): Promise<Resource<ClientData>> {
  const result = await apiRequest<{ data: ClientData }>(`/clients/${clientId}`, { signal });
  return { value: result.data.data, etag: result.response.headers.get("ETag") ?? "" };
}

export async function listEquipment(
  clientId: string,
  params: ListParams,
  signal?: AbortSignal,
): Promise<EquipmentPage> {
  return (
    await apiRequest<EquipmentPage>(`/clients/${clientId}/equipment?${query(params)}`, { signal })
  ).data;
}

export async function getEquipment(
  clientId: string,
  equipmentId: string,
  signal?: AbortSignal,
): Promise<Resource<EquipmentData>> {
  const result = await apiRequest<{ data: EquipmentData }>(
    `/clients/${clientId}/equipment/${equipmentId}`,
    { signal },
  );
  return { value: result.data.data, etag: result.response.headers.get("ETag") ?? "" };
}

export async function getTimeline(
  clientId: string,
  page: number,
  signal?: AbortSignal,
): Promise<TimelinePage> {
  return (
    await apiRequest<TimelinePage>(`/clients/${clientId}/timeline?page=${page}&page_size=20`, {
      signal,
    })
  ).data;
}

export async function mutate<T>(
  path: string,
  method: "POST" | "PATCH",
  body: Record<string, unknown>,
  csrf: string,
  etag?: string,
): Promise<Resource<T>> {
  const result = await apiRequest<{ data: T }>(
    path,
    {
      method,
      headers: etag ? { "If-Match": etag } : undefined,
      body: JSON.stringify(body),
    },
    csrf,
  );
  return { value: result.data.data, etag: result.response.headers.get("ETag") ?? "" };
}
