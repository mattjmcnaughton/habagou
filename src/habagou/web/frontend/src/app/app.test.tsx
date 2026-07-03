import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import type { ProgressReset } from "../lib/api";
import { API_V1_BASE } from "../lib/api";
import { server } from "../mocks/server";
import { App } from "./app";

describe("App", () => {
  it("[WF-02] renders pack cards with progress badges", async () => {
    render(<App />);

    expect(await screen.findByRole("heading", { name: "Habagou" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Choose a pack" })).toBeTruthy();
    expect(screen.getByText("哈巴狗")).toBeTruthy();
    expect(
      await screen.findByRole("link", {
        name: "Numbers pack, 5 characters, 2 sentences",
      }),
    ).toBeTruthy();
    expect(screen.getByText("✓ trace")).toBeTruthy();
  });

  it("[WF-02] navigates from home to a pack screen", async () => {
    render(<App />);

    fireEvent.click(
      await screen.findByRole("link", {
        name: "Greetings pack, 5 characters, 3 sentences",
      }),
    );

    expect(await screen.findByRole("heading", { name: "Greetings" })).toBeTruthy();
    expect(screen.getByTitle("nǐ · you")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Trace. Write each character stroke by stroke" }),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: "‹ All packs" })).toBeTruthy();
  });

  it("[WF-06] prefetches pack and sentence-only stroke data", async () => {
    window.history.pushState({}, "", "/packs/greetings");
    const strokeRequests: string[] = [];
    server.use(
      http.get(`${API_V1_BASE}/characters/:hanzi/strokes`, ({ params }) => {
        strokeRequests.push(String(params.hanzi));
        return HttpResponse.json({
          strokes: ["M 0 0 L 10 10"],
          medians: [
            [
              [0, 0],
              [10, 10],
            ],
          ],
        });
      }),
    );

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Greetings" })).toBeTruthy();
    await waitFor(() => {
      expect(strokeRequests).toContain("你");
      expect(strokeRequests).toContain("很");
    });
  });

  it("[WF-07] shows per-activity progress on the pack screen", async () => {
    window.history.pushState({}, "", "/packs/numbers");

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Numbers" })).toBeTruthy();
    expect(
      screen.getByRole("link", {
        name: "Trace, completed. Write each character stroke by stroke",
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Match. Pair characters with their meanings" }),
    ).toBeTruthy();
  });

  it("[WF-08] confirms and clears pack progress", async () => {
    window.history.pushState({}, "", "/packs/numbers");
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const resetRequest = vi.fn();
    server.use(
      http.delete(`${API_V1_BASE}/progress/packs/:slug`, ({ params }) => {
        resetRequest(params.slug);
        const reset: ProgressReset = {
          pack_slug: String(params.slug),
          deleted_count: 1,
          progress: {
            trace: { completed: false, completion_count: 0, best_duration_ms: null },
            match: { completed: false, completion_count: 0, best_duration_ms: null },
            sentence: { completed: false, completion_count: 0, best_duration_ms: null },
          },
        };
        return HttpResponse.json<ProgressReset>(reset);
      }),
    );

    render(<App />);

    expect(
      await screen.findByRole("link", {
        name: "Trace, completed. Write each character stroke by stroke",
      }),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Reset progress for this pack" }));

    expect(await screen.findByText("Progress reset. 1 completion cleared.")).toBeTruthy();
    expect(resetRequest).toHaveBeenCalledWith("numbers");
    await waitFor(() => {
      expect(
        screen.queryByRole("link", {
          name: "Trace, completed. Write each character stroke by stroke",
        }),
      ).toBeNull();
    });
  });
});
