import { render, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { App } from "../app/app";
import { API_V1_BASE } from "../lib/api";
import { server } from "../mocks/server";

function renderBench() {
  window.history.pushState({}, "", "/packs");
  render(<App />);
}

describe("Bench — Browse the library entry point", () => {
  it("[WF-LIB] always shows the library card, linking to /packs/library", async () => {
    renderBench();

    const link = await screen.findByRole("link", { name: /browse the library/i });
    expect(link.getAttribute("href")).toBe("/packs/library");
    expect(screen.getByText("Enable curated packs from the library.")).toBeTruthy();
  });

  it("[WF-LIB] no longer offers the AI create card on the bench, even with generation enabled", async () => {
    renderBench();

    // Wait for the bench to render before asserting the card is absent. The
    // default status handler reports generation enabled, so this pins the AI
    // entry point's demotion into the library.
    expect(await screen.findByRole("link", { name: /Greetings pack/ })).toBeTruthy();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByRole("link", { name: /create a pack/i })).toBeNull();
    expect(screen.getByRole("link", { name: /browse the library/i })).toBeTruthy();
  });

  it("[WF-LIB] keeps the library card when generation is not configured", async () => {
    server.use(
      http.get(`${API_V1_BASE}/generation/status`, () => HttpResponse.json({ enabled: false })),
    );

    renderBench();

    // The library card is not gated on generation status.
    expect(await screen.findByRole("link", { name: /browse the library/i })).toBeTruthy();
    expect(screen.queryByRole("link", { name: /create a pack/i })).toBeNull();
  });
});
