import { afterEach, describe, expect, it, vi } from "vitest";
import { apiFetch, createCompletion, listPacks } from "./api";

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
      }),
    );

    await expect(apiFetch("/readyz")).rejects.toThrow("API error: 503 Service Unavailable");
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
});
