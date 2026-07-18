import type { components } from "./api-types";
import type { CompletePathItemResponse, PathResponse } from "./path-types";
import type { CharacterJson } from "hanzi-writer";

const API_BASE = import.meta.env?.VITE_API_URL ?? "";
export const API_V1_BASE = "/api/v1";

// Page size for paginated Path reads (GET /path cursor pages).
export const PATH_PAGE_LIMIT = 6;

export type PackSummary = components["schemas"]["PackSummaryDTO"];
export type PackDetail = components["schemas"]["PackDetailDTO"];
export type PackProgress = components["schemas"]["PackProgressResponseDTO"];
export type CompletionCreate = components["schemas"]["CompletionCreateDTO"];
export type CompletionResponse = components["schemas"]["CompletionResponseDTO"];
export type ProgressReset = components["schemas"]["ProgressResetDTO"];
export type ProgressSummary = components["schemas"]["ProgressSummaryDTO"];
export type StrokeData = CharacterJson;
export type AuthUser = components["schemas"]["UserDTO"];
export type AuthSession = components["schemas"]["SessionDTO"];
export type GenerationStatus = components["schemas"]["GenerationStatusDTO"];
export type PackDraft = components["schemas"]["PackDraft"];
export type DraftCharacter = components["schemas"]["PackDraftCharacter"];
export type DraftSentence = components["schemas"]["PackDraftSentence"];
export type GenerationDraftResponse = components["schemas"]["GenerationDraftResponseDTO"];

export type {
  CompletePathItemBody,
  CompletePathItemResponse,
  DailyGoal,
  PathActivity,
  PathCharacter,
  PathContent,
  PathDue,
  PathItem,
  PathItemKind,
  PathItemState,
  PathPack,
  PathResponse,
  PathSentence,
} from "./path-types";

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
  if (res.status === 204) {
    return undefined as T;
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

export function getAuthSession(): Promise<AuthSession> {
  return apiFetch<AuthSession>(apiV1Path("/auth/session"));
}

export async function logout(): Promise<void> {
  await apiFetch<void>("/auth/logout", { method: "POST" });
}

export function getPack(packId: string): Promise<PackDetail> {
  return apiFetch<PackDetail>(apiV1Path(`/packs/${encodeURIComponent(packId)}`));
}

export async function deletePack(packId: string): Promise<void> {
  await apiFetch<void>(apiV1Path(`/packs/${encodeURIComponent(packId)}`), {
    method: "DELETE",
  });
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

export function getPackProgress(packId: string): Promise<PackProgress> {
  return apiFetch<PackProgress>(apiV1Path(`/progress/packs/${encodeURIComponent(packId)}`));
}

export function getProgressSummary(): Promise<ProgressSummary> {
  const tzOffsetMinutes = new Date().getTimezoneOffset();
  return apiFetch<ProgressSummary>(
    apiV1Path(`/progress/summary?tz_offset_minutes=${tzOffsetMinutes}`),
  );
}

export function resetPackProgress(packId: string): Promise<ProgressReset> {
  return apiFetch<ProgressReset>(apiV1Path(`/progress/packs/${encodeURIComponent(packId)}`), {
    method: "DELETE",
  });
}

export function getPath({
  cursor,
  limit,
}: { cursor?: number; limit?: number } = {}): Promise<PathResponse> {
  const params = new URLSearchParams();
  if (cursor !== undefined) {
    params.set("cursor", String(cursor));
  }
  if (limit !== undefined) {
    params.set("limit", String(limit));
  }
  const query = params.toString();
  return apiFetch<PathResponse>(apiV1Path(query ? `/path?${query}` : "/path"));
}

export function getGenerationStatus(): Promise<GenerationStatus> {
  return apiFetch<GenerationStatus>(apiV1Path("/generation/status"));
}

export function generateDraft(
  topic: string,
  history?: unknown[],
): Promise<GenerationDraftResponse> {
  // JSON.stringify drops undefined properties, so a first-turn `history` of
  // undefined is omitted from the wire body and matches GenerationDraftRequestDTO.
  const body: components["schemas"]["GenerationDraftRequestDTO"] = { topic, history };
  return apiFetch<GenerationDraftResponse>(apiV1Path("/generation/draft"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function saveGeneratedPack(draft: PackDraft): Promise<PackDetail> {
  const body: components["schemas"]["GenerationSavePackRequestDTO"] = { draft };
  return apiFetch<PackDetail>(apiV1Path("/generation/packs"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function completePathItem(
  itemId: string,
  body: { duration_ms: number },
): Promise<CompletePathItemResponse> {
  return apiFetch<CompletePathItemResponse>(
    apiV1Path(`/path/items/${encodeURIComponent(itemId)}/complete`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}
