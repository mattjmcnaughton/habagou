import type { Components } from "./api-types";
import type { CharacterJson } from "hanzi-writer";

const API_BASE = import.meta.env.VITE_API_URL ?? "";
export const API_V1_BASE = "/api/v1";

export type PackSummary = Components["schemas"]["PackSummaryDTO"];
export type PackDetail = Components["schemas"]["PackDetailDTO"];
export type PackProgress = Components["schemas"]["PackProgressResponseDTO"];
export type CompletionCreate = Components["schemas"]["CompletionCreateDTO"];
export type CompletionResponse = Components["schemas"]["CompletionResponseDTO"];
export type ProgressReset = Components["schemas"]["ProgressResetDTO"];
export type StrokeData = CharacterJson;

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
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

export function resetPackProgress(slug: string): Promise<ProgressReset> {
  return apiFetch<ProgressReset>(apiV1Path(`/progress/packs/${encodeURIComponent(slug)}`), {
    method: "DELETE",
  });
}
