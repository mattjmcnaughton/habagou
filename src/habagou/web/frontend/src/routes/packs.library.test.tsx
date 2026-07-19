import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { App } from "../app/app";
import { API_V1_BASE } from "../lib/api";
import { libraryCategories, setMockPackEnabled } from "../mocks/handlers";
import { server } from "../mocks/server";

// The disabled-by-default, non-starter fixture tests toggle (../mocks/handlers.ts).
const fruitPack = libraryCategories
  .flatMap((category) => category.packs)
  .find((pack) => pack.title === "Fruit");
if (!fruitPack) {
  throw new Error("Fruit library fixture missing");
}
const FRUIT_ID = fruitPack.id;

function renderLibraryPage() {
  window.history.pushState({}, "", "/packs/library");
  render(<App />);
}

describe("Pack library", () => {
  afterEach(() => {
    // The enablement handler mutates the shared fixtures; restore the default.
    setMockPackEnabled(FRUIT_ID, false);
  });

  it("[WF-LIB] renders categories in server order with pack rows", async () => {
    renderLibraryPage();

    expect(await screen.findByRole("heading", { name: "Essentials" })).toBeTruthy();
    // Category headings render in the order the server sent them.
    const titles = screen
      .getAllByRole("heading", { level: 2 })
      .map((heading) => heading.textContent);
    expect(titles.indexOf("Essentials")).toBeGreaterThanOrEqual(0);
    expect(titles.indexOf("Essentials")).toBeLessThan(titles.indexOf("Food & Drink"));

    // A row links to the pack's preview and carries description + counts.
    const row = screen.getByRole("link", {
      name: "Greetings pack, 5 characters, 3 sentences",
    });
    expect(row.getAttribute("href")).toBe(`/packs/${libraryCategories[0].packs[0].id}`);
    expect(screen.getByText("First words for meeting people.")).toBeTruthy();

    // Enabled starters show the quiet toggle; the disabled pack the jade one.
    expect(screen.getByRole("button", { name: "Disable Greetings" }).textContent).toContain(
      "Enabled ✓",
    );
    expect(screen.getByRole("button", { name: "Enable Fruit" }).textContent).toContain("Enable");
  });

  it("[WF-LIB] enables a pack optimistically and fires the PUT", async () => {
    const putRequests: { packId: string; enabled: boolean }[] = [];
    // Hold the server response behind an explicit gate so the flip observed
    // below can only come from the optimistic ["library"] cache update, not
    // a refetch — no timing assumptions, immune to slow runners.
    let releaseServer!: () => void;
    const serverGate = new Promise<void>((resolve) => {
      releaseServer = resolve;
    });
    server.use(
      http.put(`${API_V1_BASE}/packs/:packId/enabled`, async ({ params, request }) => {
        const body = (await request.json()) as { enabled: boolean };
        await serverGate;
        putRequests.push({ packId: String(params.packId), enabled: body.enabled });
        setMockPackEnabled(String(params.packId), body.enabled);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderLibraryPage();

    fireEvent.click(await screen.findByRole("button", { name: "Enable Fruit" }));

    // Optimistic: the toggle flips while the server is still gated.
    expect(await screen.findByRole("button", { name: "Disable Fruit" })).toBeTruthy();
    expect(putRequests).toHaveLength(0);

    releaseServer();
    await waitFor(() => expect(putRequests).toEqual([{ packId: FRUIT_ID, enabled: true }]));
    // Still flipped once the settle-time refetch reconciles with the server.
    expect(await screen.findByRole("button", { name: "Disable Fruit" })).toBeTruthy();
  });

  it("[WF-LIB] filters rows on title and description and hides empty categories", async () => {
    renderLibraryPage();
    expect(await screen.findByRole("link", { name: /Greetings pack/ })).toBeTruthy();

    const input = screen.getByRole("searchbox", { name: "Search the library" });
    fireEvent.change(input, { target: { value: "greet" } });

    expect(screen.getByRole("link", { name: /Greetings pack/ })).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Numbers pack/ })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Food & Drink" })).toBeNull();

    // Description text matches too (case-insensitive).
    fireEvent.change(input, { target: { value: "MARKET STALL" } });
    expect(screen.getByRole("link", { name: /Fruit pack/ })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Essentials" })).toBeNull();
  });

  it("[WF-LIB] offers the AI fallback in the empty state when generation is enabled", async () => {
    renderLibraryPage();
    expect(await screen.findByRole("link", { name: /Greetings pack/ })).toBeTruthy();

    fireEvent.change(screen.getByRole("searchbox", { name: "Search the library" }), {
      target: { value: "zzz" },
    });

    expect(screen.getByText("No packs match your search.")).toBeTruthy();
    const fallback = screen.getByRole("link", {
      name: "Can't find it? Create your own pack with AI",
    });
    expect(fallback.getAttribute("href")).toBe("/packs/generate");
  });

  it("[WF-LIB] shows the Create a pack card at the bottom when generation is enabled", async () => {
    renderLibraryPage();

    const card = await screen.findByRole("link", { name: /create a pack/i });
    expect(card.getAttribute("href")).toBe("/packs/generate");
    expect(screen.getByText("AI · BETA")).toBeTruthy();
  });

  it("[WF-LIB] hides every AI entry point when generation is not configured", async () => {
    server.use(
      http.get(`${API_V1_BASE}/generation/status`, () => HttpResponse.json({ enabled: false })),
    );
    renderLibraryPage();
    expect(await screen.findByRole("link", { name: /Greetings pack/ })).toBeTruthy();

    // The status query settles independently of the library query, so flush
    // pending microtasks/queries before asserting the card never appears.
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByRole("link", { name: /create a pack/i })).toBeNull();

    // The zero-match empty state stays, but without the AI fallback link.
    fireEvent.change(screen.getByRole("searchbox", { name: "Search the library" }), {
      target: { value: "zzz" },
    });
    expect(screen.getByText("No packs match your search.")).toBeTruthy();
    expect(screen.queryByRole("link", { name: /create your own pack/i })).toBeNull();
  });
});
