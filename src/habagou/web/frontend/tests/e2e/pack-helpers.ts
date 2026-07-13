import { expect, type APIRequestContext } from "@playwright/test";

// Packs are addressed by id (UUID); the seed slug is no longer on the API
// surface. Tests resolve the id they need from the catalog by the pack's
// (stable) display title.
export type PackRef = { id: string; title: string };

export async function fetchPacks(request: APIRequestContext): Promise<PackRef[]> {
  const response = await request.get("/api/v1/packs");
  expect(response.ok(), await response.text()).toBeTruthy();
  const packs = (await response.json()) as PackRef[];
  return packs.map((pack) => ({ id: pack.id, title: pack.title }));
}

export async function packIdByTitle(request: APIRequestContext, title: string): Promise<string> {
  const packs = await fetchPacks(request);
  const pack = packs.find((entry) => entry.title === title);
  if (!pack) {
    throw new Error(`pack not found by title: ${title}`);
  }
  return pack.id;
}

// Clear every pack's completions for the signed-in user, keeping specs
// independent regardless of what earlier runs recorded.
export async function resetAllPacks(request: APIRequestContext): Promise<void> {
  const packs = await fetchPacks(request);
  for (const pack of packs) {
    const response = await request.delete(`/api/v1/progress/packs/${pack.id}`);
    expect(response.ok()).toBe(true);
  }
}
