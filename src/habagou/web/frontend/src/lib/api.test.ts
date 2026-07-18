import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  generationDraftFailure,
  generationHistory,
  packDraft,
  practiceHistory,
  practiceOpeningTurn,
} from "../mocks/handlers";
import { server } from "../mocks/server";
import {
  type ApiError,
  API_V1_BASE,
  apiFetch,
  completePathItem,
  createCompletion,
  generateDraft,
  getGenerationStatus,
  getPath,
  getProgressSummary,
  listPacks,
  logout,
  practiceTurn,
  saveGeneratedPack,
} from "./api";

describe("apiFetch", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
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
        activity: "trace",
        duration_ms: 100,
        progress: {},
      }),
    });
    vi.stubGlobal("fetch", fetch);

    await createCompletion({
      pack_id: "11111111-1111-4111-8111-111111111111",
      activity: "trace",
      duration_ms: 100,
    });

    expect(fetch).toHaveBeenCalledWith("/api/v1/progress/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pack_id: "11111111-1111-4111-8111-111111111111",
        activity: "trace",
        duration_ms: 100,
      }),
    });
  });

  it("requests a path page with cursor and limit query params", async () => {
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
    });
    vi.stubGlobal("fetch", fetch);

    await getPath({ cursor: 12, limit: 20 });

    expect(fetch).toHaveBeenCalledWith("/api/v1/path?cursor=12&limit=20", undefined);
  });

  it("requests the path with no query params when none are given", async () => {
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
    });
    vi.stubGlobal("fetch", fetch);

    await getPath();

    expect(fetch).toHaveBeenCalledWith("/api/v1/path", undefined);
  });

  it("posts a path item completion as JSON", async () => {
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({
        daily: { completed: 3, target: 3 },
        streak: 12,
        item_id: "item-1",
        next_item_id: "item-2",
      }),
    });
    vi.stubGlobal("fetch", fetch);

    await completePathItem("item-1", { duration_ms: 41200 });

    expect(fetch).toHaveBeenCalledWith("/api/v1/path/items/item-1/complete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ duration_ms: 41200 }),
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

describe("generation API", () => {
  it("[WF-15] reads the generation status flag", async () => {
    // The default (non-admin) status carries no model-picker data.
    await expect(getGenerationStatus()).resolves.toEqual({
      enabled: true,
      models: null,
      default_model: null,
    });
  });

  it("[WF-15] drafts a pack and returns the draft with opaque history", async () => {
    const result = await generateDraft("restaurant");

    expect(result.draft.title).toBe(packDraft.title);
    expect(result.draft.coverage_note).toBe(packDraft.coverage_note);
    expect(result.history).toEqual(generationHistory);
  });

  it("[WF-15] omits history on the first turn", async () => {
    let received: unknown;
    server.use(
      http.post(`${API_V1_BASE}/generation/draft`, async ({ request }) => {
        received = await request.json();
        return HttpResponse.json({ draft: packDraft, history: [] });
      }),
    );

    await generateDraft("restaurant");

    expect(received).toEqual({ topic: "restaurant" });
  });

  it("[WF-15] replays prior history on a refinement turn", async () => {
    let received: unknown;
    server.use(
      http.post(`${API_V1_BASE}/generation/draft`, async ({ request }) => {
        received = await request.json();
        return HttpResponse.json({ draft: packDraft, history: [] });
      }),
    );

    await generateDraft("add drinks", generationHistory);

    expect(received).toEqual({ topic: "add drinks", history: generationHistory });
  });

  it("[WF-15] saves a generated pack and returns pack detail", async () => {
    const result = await saveGeneratedPack(packDraft);

    expect(result.title).toBe(packDraft.title);
    expect(result.char_count).toBe(packDraft.characters.length);
    expect(result.id).toBeTruthy();
  });

  it("[WF-15] surfaces a 429 rate limit as an ApiError", async () => {
    server.use(generationDraftFailure(429));

    await expect(generateDraft("restaurant")).rejects.toMatchObject({
      code: "rate_limited",
      name: "ApiError",
      status: 429,
    } satisfies Partial<ApiError>);
  });

  it("[WF-15] includes the admin model override in the draft body", async () => {
    let received: unknown;
    server.use(
      http.post(`${API_V1_BASE}/generation/draft`, async ({ request }) => {
        received = await request.json();
        return HttpResponse.json({ draft: packDraft, history: [] });
      }),
    );

    await generateDraft("restaurant", generationHistory, "anthropic/claude-sonnet-5");

    expect(received).toEqual({
      topic: "restaurant",
      history: generationHistory,
      model: "anthropic/claude-sonnet-5",
    });
  });

  it("[WF-15] omits the model key entirely when no override is given", async () => {
    let received: unknown;
    server.use(
      http.post(`${API_V1_BASE}/generation/draft`, async ({ request }) => {
        received = await request.json();
        return HttpResponse.json({ draft: packDraft, history: [] });
      }),
    );

    await generateDraft("restaurant", generationHistory);

    // toEqual is key-exact here: no `model` (or `model: undefined`) survives
    // serialization, matching the DTO's "absent means server default".
    expect(received).toEqual({ topic: "restaurant", history: generationHistory });
  });
});

describe("practice API", () => {
  it("[WF-16] omits history and model on a first turn", async () => {
    let received: unknown;
    server.use(
      http.post(`${API_V1_BASE}/practice/turn`, async ({ request }) => {
        received = await request.json();
        return HttpResponse.json({ turn: practiceOpeningTurn, history: practiceHistory });
      }),
    );

    await practiceTurn("ordering food");

    expect(received).toEqual({ message: "ordering food" });
  });

  it("[WF-16] includes the admin model override in the turn body", async () => {
    let received: unknown;
    server.use(
      http.post(`${API_V1_BASE}/practice/turn`, async ({ request }) => {
        received = await request.json();
        return HttpResponse.json({ turn: practiceOpeningTurn, history: practiceHistory });
      }),
    );

    await practiceTurn("我要吃饭", practiceHistory, "minimax/minimax-m3");

    expect(received).toEqual({
      message: "我要吃饭",
      history: practiceHistory,
      model: "minimax/minimax-m3",
    });
  });
});
