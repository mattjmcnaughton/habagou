import type { components } from "./api-types";
import type { CharacterJson } from "hanzi-writer";

const API_BASE = import.meta.env.VITE_API_URL ?? "";
export const API_V1_BASE = "/api/v1";

export type PackSummary = components["schemas"]["PackSummaryDTO"];
export type PackDetail = components["schemas"]["PackDetailDTO"];
export type PackProgress = components["schemas"]["PackProgressResponseDTO"];
export type CompletionCreate = components["schemas"]["CompletionCreateDTO"];
export type CompletionResponse = components["schemas"]["CompletionResponseDTO"];
export type ProgressReset = components["schemas"]["ProgressResetDTO"];
export type ProgressSummary = components["schemas"]["ProgressSummaryDTO"];
export type StrokeData = CharacterJson;

type ErrorEnvelope = {
  error?: {
    code?: string;
    message?: string;
    request_id?: string;
    details?: unknown;
  };
};

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string,
    public readonly requestId?: string,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    const envelope = await parseErrorEnvelope(res);
    const code = envelope.error?.code ?? `http_${res.status}`;
    const message = envelope.error?.message ?? `API error: ${res.status} ${res.statusText}`;
    throw new ApiError(
      message,
      res.status,
      code,
      envelope.error?.request_id,
      envelope.error?.details,
    );
  }
  return res.json() as Promise<T>;
}

async function parseErrorEnvelope(res: Response): Promise<ErrorEnvelope> {
  try {
    return (await res.json()) as ErrorEnvelope;
  } catch {
    return {};
  }
}

export function apiV1Path(path: `/${string}`): string {
  return `${API_V1_BASE}${path}`;
}

export function listPacks(): Promise<PackSummary[]> {
  return apiFetch<PackSummary[]>(apiV1Path("/packs"));
}

export function getPack(slug: string): Promise<PackDetail> {
  return apiFetch<PackDetail>(apiV1Path(`/packs/${encodeURIComponent(slug)}`));
}

export function getCharacterStrokes(hanzi: string): Promise<StrokeData> {
  return apiFetch<StrokeData>(apiV1Path(`/characters/${encodeURIComponent(hanzi)}/strokes`));
}

export function createCompletion(completion: CompletionCreate): Promise<CompletionResponse> {
  return apiFetch<CompletionResponse>(apiV1Path("/progress/completions"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(completion),
  });
}

export function getPackProgress(slug: string): Promise<PackProgress> {
  return apiFetch<PackProgress>(apiV1Path(`/progress/packs/${encodeURIComponent(slug)}`));
}

export function getProgressSummary(): Promise<ProgressSummary> {
  const tzOffsetMinutes = new Date().getTimezoneOffset();
  return apiFetch<ProgressSummary>(
    apiV1Path(`/progress/summary?tz_offset_minutes=${tzOffsetMinutes}`),
  );
}

export function resetPackProgress(slug: string): Promise<ProgressReset> {
  return apiFetch<ProgressReset>(apiV1Path(`/progress/packs/${encodeURIComponent(slug)}`), {
    method: "DELETE",
  });
}
