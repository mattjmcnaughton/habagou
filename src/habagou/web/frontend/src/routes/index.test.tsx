import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../app/app";

function renderPath() {
  window.history.pushState({}, "", "/");
  render(<App />);
}

describe("Path screen", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("[WF-PATH] renders the hero with daily goal, streak, and due chips", async () => {
    renderPath();

    expect(await screen.findByTestId("path-shell")).toBeTruthy();
    // daily = { completed: 2, target: 3 } -> 1 lesson remaining, ring "2/3".
    expect(await screen.findByText("1 lesson to today's goal")).toBeTruthy();
    expect(screen.getByTestId("path-goal-ring-label").textContent).toBe("2/3");
    expect(screen.getByText("12-day")).toBeTruthy();
    expect(screen.getByText("Due · 1 new, 2 reviews")).toBeTruthy();
  });

  it("[WF-PATH] renders done, current, and locked lesson node states", async () => {
    renderPath();

    await screen.findByTestId("path-timeline");
    const nodes = await screen.findAllByTestId("path-node");
    // First page (limit 6) holds items 1..6: two done, one current, three locked.
    const states = nodes.map((node) => node.getAttribute("data-state"));
    expect(states).toEqual(["done", "done", "current", "locked", "locked", "locked"]);

    const doneDot = screen.getAllByTestId("path-node-dot")[0];
    expect(doneDot.getAttribute("data-state")).toBe("done");
    // Done nodes show a completion check.
    expect(screen.getAllByLabelText("completed").length).toBeGreaterThan(0);
  });

  it("[WF-PATH] exposes a Start button only on the current node", async () => {
    renderPath();

    const startLinks = await screen.findAllByRole("link", { name: /Start lesson/ });
    expect(startLinks).toHaveLength(1);
    expect(startLinks[0].getAttribute("href")).toBe("/lesson/aaaaaaaa-0000-4000-8000-000000000003");

    // The current node's card is the one carrying the Start button.
    const currentNode = (await screen.findAllByTestId("path-node")).find(
      (node) => node.getAttribute("data-state") === "current",
    );
    expect(currentNode).toBeTruthy();
    expect(
      within(currentNode as HTMLElement).getByRole("link", { name: /Start lesson/ }),
    ).toBeTruthy();
  });

  it("[WF-PATH] renders the unit-divider pill from unit_label", async () => {
    renderPath();

    expect(await screen.findByText("UNIT 1 · WARMING UP")).toBeTruthy();
    const dividers = screen.getAllByTestId("path-unit-divider");
    expect(dividers.length).toBeGreaterThanOrEqual(1);
  });

  it("[WF-PATH] fetches the next page when the footer trigger intersects", async () => {
    // jsdom lacks IntersectionObserver: stub one that fires immediately on observe.
    class MockIntersectionObserver {
      private readonly cb: IntersectionObserverCallback;
      constructor(cb: IntersectionObserverCallback) {
        this.cb = cb;
      }
      observe() {
        this.cb(
          [{ isIntersecting: true } as IntersectionObserverEntry],
          this as unknown as IntersectionObserver,
        );
      }
      unobserve() {}
      disconnect() {}
      takeRecords() {
        return [];
      }
    }
    vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);

    renderPath();

    // Page 1 loads items 1..6 (limit 6).
    await waitFor(() => expect(screen.getAllByTestId("path-node").length).toBe(6));
    // Intersection triggers page 2 (items 7..8), so all 8 nodes render.
    await waitFor(() => expect(screen.getAllByTestId("path-node").length).toBe(8));
    // A distinctive page-2 item (sentence "一二三") is now present.
    expect(screen.getByText("一二三")).toBeTruthy();
  });
});
