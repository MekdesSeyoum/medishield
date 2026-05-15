import type { CaseRecord, PaginatedCasesResponse } from "./types";

const BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${init?.method ?? "GET"} ${path} → ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export function getCases(
  page = 1,
  status?: string,
  pageSize = 50
): Promise<PaginatedCasesResponse> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (status) params.set("status", status);
  return apiFetch<PaginatedCasesResponse>(`/cases/?${params}`);
}

export function getCase(caseId: string): Promise<CaseRecord> {
  return apiFetch<CaseRecord>(`/cases/${caseId}`);
}

export function getDocumentUrl(
  caseId: string
): Promise<{ url: string; mime_type: string }> {
  return apiFetch<{ url: string; mime_type: string }>(
    `/cases/${caseId}/document-url`
  );
}

export function overrideDecision(
  caseId: string,
  decision: "APPROVE" | "REJECT",
  reason: string
): Promise<CaseRecord> {
  return apiFetch<CaseRecord>(`/cases/${caseId}/decision`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, reason }),
  });
}
