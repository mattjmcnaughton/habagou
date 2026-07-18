import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../app/app";
import type { PackDetail, PackSummary } from "../lib/api";
import { API_V1_BASE } from "../lib/api";
import { packDeleteFailure } from "../mocks/handlers";
import { server } from "../mocks/server";

// The curated Greetings fixture (owned: false) mirrors ../mocks/handlers.ts.
const GREETINGS_ID = "11111111-1111-4111-8111-111111111111";

// A user-owned (AI-generated) pack the signed-in user is allowed to delete. It
// is not part of the default fixtures, so tests install it via `server.use`.
const OWNED_ID = "33333333-3333-4333-8333-333333333333";
const ownedSummary: PackSummary = {
  id: OWNED_ID,
  title: "My Custom Pack",
  glyph: "造",
  color: "#c4633f",
  char_count: 1,
  sentence_count: 0,
  owned: true,
  progress: {
    trace: { completed: false, completion_count: 0, best_duration_ms: null },
    match: { completed: false, completion_count: 0, best_duration_ms: null },
    sentence: { completed: false, completion_count: 0, best_duration_ms: null },
  },
};
const ownedDetail: PackDetail = {
  ...ownedSummary,
  characters: [{ hanzi: "造", pinyin: "zào", meaning: "to create" }],
  sentences: [],
};

function serveOwnedPack() {
  return http.get(`${API_V1_BASE}/packs/${OWNED_ID}`, () =>
    HttpResponse.json<PackDetail>(ownedDetail),
  );
}

describe("Pack detail — delete pack", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("[WF-DELETE] hides the delete button for a curated pack the user does not own", async () => {
    window.history.pushState({}, "", `/packs/${GREETINGS_ID}`);

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Greetings" })).toBeTruthy();
    // The reset danger-zone is still present, but no delete affordance for a
    // curated (unowned) pack.
    expect(screen.getByRole("button", { name: "Reset progress for this pack" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Delete this pack" })).toBeNull();
  });

  it("[WF-DELETE] shows the delete button for an owned pack", async () => {
    window.history.pushState({}, "", `/packs/${OWNED_ID}`);
    server.use(serveOwnedPack());

    render(<App />);

    expect(await screen.findByRole("heading", { name: "My Custom Pack" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Delete this pack" })).toBeTruthy();
  });

  it("[WF-DELETE] fires no request when the confirmation is cancelled", async () => {
    window.history.pushState({}, "", `/packs/${OWNED_ID}`);
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const deleteRequest = vi.fn();
    server.use(
      serveOwnedPack(),
      http.delete(`${API_V1_BASE}/packs/:packId`, ({ params }) => {
        deleteRequest(params.packId);
        return new HttpResponse(null, { status: 204 });
      }),
    );

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Delete this pack" }));

    expect(window.confirm).toHaveBeenCalledWith(
      'Delete "My Custom Pack"? This permanently removes the pack and your progress for it.',
    );
    // Give any stray request a chance to land, then confirm none was made.
    await new Promise((r) => setTimeout(r, 0));
    expect(deleteRequest).not.toHaveBeenCalled();
    // Still on the detail screen.
    expect(screen.getByRole("heading", { name: "My Custom Pack" })).toBeTruthy();
  });

  it("[WF-DELETE] deletes an owned pack, lands on the path shell, and drops it from the library", async () => {
    window.history.pushState({}, "", `/packs/${OWNED_ID}`);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const deleteRequest = vi.fn();
    let deleted = false;
    server.use(
      serveOwnedPack(),
      http.delete(`${API_V1_BASE}/packs/:packId`, ({ params }) => {
        deleteRequest(params.packId);
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
      // The library reflects server state: the owned pack is present until it is
      // deleted, then gone on the invalidation-driven refetch.
      http.get(`${API_V1_BASE}/packs`, () =>
        HttpResponse.json<PackSummary[]>(deleted ? [] : [ownedSummary]),
      ),
    );

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Delete this pack" }));

    // The delete hit the endpoint with the pack id and the app navigated home.
    await waitFor(() => expect(deleteRequest).toHaveBeenCalledWith(OWNED_ID));
    expect(await screen.findByTestId("path-shell")).toBeTruthy();

    // Navigating to the library reflects the invalidated ["packs"] query: the
    // deleted pack is no longer listed.
    const nav = screen.getByRole("navigation", { name: "Primary" });
    fireEvent.click(within(nav).getByRole("link", { name: "Packs" }));
    expect(await screen.findByRole("heading", { name: "Choose a pack" })).toBeTruthy();
    await waitFor(() =>
      expect(screen.queryByRole("link", { name: /My Custom Pack pack/ })).toBeNull(),
    );
  });

  it("[WF-DELETE] surfaces an inline error and retries a failed delete", async () => {
    window.history.pushState({}, "", `/packs/${OWNED_ID}`);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    server.use(serveOwnedPack(), packDeleteFailure(503));

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Delete this pack" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Pack could not be deleted.");

    // The retry succeeds: swap in a success handler, retry, and land home.
    const deleteRequest = vi.fn();
    server.use(
      http.delete(`${API_V1_BASE}/packs/:packId`, ({ params }) => {
        deleteRequest(params.packId);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry delete" }));

    await waitFor(() => expect(deleteRequest).toHaveBeenCalledWith(OWNED_ID));
    expect(await screen.findByTestId("path-shell")).toBeTruthy();
  });
});
