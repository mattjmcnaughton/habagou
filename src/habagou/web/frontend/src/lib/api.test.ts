import { afterEach, describe, expect, it, vi } from "vitest";
import {
  type ApiError,
  apiFetch,
  createCompletion,
  getProgressSummary,
  listPacks,
  logout,
} from "./api";

describe("apiFetch", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns parsed JSON for successful responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: vi.fn().mockResolvedValue({ status: "ok" }),
      }),
    );

    await expect(apiFetch("/healthz")).resolves.toEqual({ status: "ok" });
  });

  it("throws for unsuccessful responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        statusText: "Service Unavailable",
        json: vi.fn().mockResolvedValue({
          error: {
            code: "database_unavailable",
            message: "database is unavailable",
            request_id: "req-1",
          },
        }),
      }),
    );

    await expect(apiFetch("/readyz")).rejects.toMatchObject({
      code: "database_unavailable",
      message: "database is unavailable",
      name: "ApiError",
      requestId: "req-1",
      status: 503,
    } satisfies Partial<ApiError>);
  });

  it("falls back to HTTP status when an error body is not JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        statusText: "Bad Gateway",
        json: vi.fn().mockRejectedValue(new Error("not json")),
      }),
    );

    await expect(apiFetch("/readyz")).rejects.toMatchObject({
      code: "http_502",
      message: "API error: 502 Bad Gateway",
      status: 502,
    } satisfies Partial<ApiError>);
  });

  it("uses the versioned API base for typed helpers", async () => {
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue([]),
    });
    vi.stubGlobal("fetch", fetch);

    await listPacks();

    expect(fetch).toHaveBeenCalledWith("/api/v1/packs", undefined);
  });

  it("handles empty 204 responses", async () => {
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
    });
    vi.stubGlobal("fetch", fetch);

    await expect(logout()).resolves.toBeUndefined();

    expect(fetch).toHaveBeenCalledWith("/auth/logout", { method: "POST" });
  });

  it("posts typed completion requests as JSON", async () => {
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({
        pack_slug: "greetings",
        activity: "trace",
        duration_ms: 100,
        progress: {},
      }),
    });
    vi.stubGlobal("fetch", fetch);

    await createCompletion({
      pack_slug: "greetings",
      activity: "trace",
      duration_ms: 100,
    });

    expect(fetch).toHaveBeenCalledWith("/api/v1/progress/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pack_slug: "greetings",
        activity: "trace",
        duration_ms: 100,
      }),
    });
  });

  it("requests progress summary with the browser timezone offset", async () => {
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({
        current_streak: 0,
        best_streak: 0,
        daily_goal: { completed: 0, target: 3 },
        activity: [],
        next_milestone: {
          target_days: 7,
          days_remaining: 7,
          progress_pct: 0,
        },
      }),
    });
    vi.stubGlobal("fetch", fetch);

    await getProgressSummary();

    expect(fetch).toHaveBeenCalledWith(
      `/api/v1/progress/summary?tz_offset_minutes=${new Date().getTimezoneOffset()}`,
      undefined,
    );
  });
});
