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

  it("[WF-11] shows a compact progress link on the home page", async () => {
    render(<App />);

    const progressLink = await screen.findByRole("link", {
      name: "Progress today, 2 of 3 complete, 12-day streak",
    });

    expect(progressLink).toBeTruthy();
    expect(progressLink.textContent).toContain("12-day");
    expect(screen.getByText("2/3 goal")).toBeTruthy();
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
      screen.getByRole("link", { name: "Match. Pair characters with their meanings" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Sentences. Write full sentences from the pack" }),
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

  it("[WF-08] shows a retry action when progress reset fails", async () => {
    window.history.pushState({}, "", "/packs/numbers");
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const resetRequest = vi.fn();
    server.use(
      http.delete(`${API_V1_BASE}/progress/packs/:slug`, ({ params }) => {
        resetRequest(params.slug);
        return HttpResponse.json(
          {
            error: {
              code: "database_unavailable",
              message: "database is unavailable",
              request_id: "req-reset",
            },
          },
          { status: 503 },
        );
      }),
    );

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Numbers" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Reset progress for this pack" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Progress could not be reset.",
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry reset" }));
    await waitFor(() => expect(resetRequest).toHaveBeenCalledTimes(2));
  });

  it("[WF-11] shows streak, goal ring and milestone from the summary API", async () => {
    window.history.pushState({}, "", "/progress");

    render(<App />);

    expect(await screen.findByText("12-day streak")).toBeTruthy();
    expect(screen.getByText((_, element) => element?.textContent === "2/3")).toBeTruthy();
    expect(screen.getByText("14-day streak")).toBeTruthy();
    expect(screen.getByText(/2 days away/)).toBeTruthy();
  });

  it("[WF-11] expands and collapses the activity heatmap", async () => {
    window.history.pushState({}, "", "/progress");

    render(<App />);

    expect(await screen.findByText("Activity")).toBeTruthy();
    const activity = screen.getByRole("button", { expanded: false });
    expect(activity.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(activity);

    expect(screen.getByText("Tap to collapse")).toBeTruthy();
    expect(screen.getByText("This month")).toBeTruthy();
    expect(screen.getByRole("button", { expanded: true })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { expanded: true }));

    expect(screen.getByText("Tap to expand")).toBeTruthy();
    expect(screen.getByRole("button", { expanded: false })).toBeTruthy();
  });

  it("[WF-11] Practice now links to the first incomplete pack", async () => {
    window.history.pushState({}, "", "/progress");

    render(<App />);

    const practiceNow = await screen.findByRole("link", { name: "Practice now" });
    expect(practiceNow.getAttribute("href")).toBe("/packs/greetings");
  });

  it("[WF-11] shows the progress error state", async () => {
    window.history.pushState({}, "", "/progress");
    server.use(
      http.get(`${API_V1_BASE}/progress/summary`, () =>
        HttpResponse.json(
          {
            error: {
              code: "database_unavailable",
              message: "database is unavailable",
              request_id: "req-progress",
            },
          },
          { status: 503 },
        ),
      ),
    );

    render(<App />);

    expect(
      await screen.findByText("Progress could not be loaded.", {}, { timeout: 3000 }),
    ).toBeTruthy();
  });
});
