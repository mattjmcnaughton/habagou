import { render, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { App } from "../app/app";
import { API_V1_BASE } from "../lib/api";
import { server } from "../mocks/server";

function renderLibrary() {
  window.history.pushState({}, "", "/packs");
  render(<App />);
}

describe("Pack library — Create a pack entry point", () => {
  it("[WF-15] surfaces the Create a pack card when generation is enabled", async () => {
    renderLibrary();

    const link = await screen.findByRole("link", { name: /create a pack/i });
    expect(link.getAttribute("href")).toBe("/packs/generate");
    expect(screen.getByText("AI · BETA")).toBeTruthy();
    expect(screen.getByText("Describe a topic — we'll draft characters & sentences.")).toBeTruthy();
  });

  it("[WF-15] hides the card when generation is not configured", async () => {
    server.use(
      http.get(`${API_V1_BASE}/generation/status`, () => HttpResponse.json({ enabled: false })),
    );

    renderLibrary();

    // Wait for the library to render before asserting the card is absent.
    expect(await screen.findByRole("link", { name: /Greetings pack/ })).toBeTruthy();
    // The status query settles independently of the packs query, so flush
    // pending microtasks/queries before asserting the card never appears.
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByRole("link", { name: /create a pack/i })).toBeNull();
  });

  it("[WF-15] hides the card and keeps the library when the status probe fails", async () => {
    server.use(
      http.get(`${API_V1_BASE}/generation/status`, () =>
        HttpResponse.json(
          {
            error: {
              code: "service_unavailable",
              message: "generation status unavailable",
              request_id: "mock-request",
            },
          },
          { status: 503 },
        ),
      ),
    );

    renderLibrary();

    // The library must be unaffected by a status probe failure.
    expect(await screen.findByRole("link", { name: /Greetings pack/ })).toBeTruthy();
    // The status query settles independently of the packs query, so flush
    // pending microtasks/queries before asserting the card never appears.
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByRole("link", { name: /create a pack/i })).toBeNull();
  });
});
