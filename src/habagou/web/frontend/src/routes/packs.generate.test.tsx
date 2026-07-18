import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { App } from "../app/app";
import { API_V1_BASE } from "../lib/api";
import {
  chatModelOptions,
  generationDraftFailure,
  generationHistory,
  generationSaveFailure,
  generationStatusAdmin,
  packDraft,
} from "../mocks/handlers";
import { server } from "../mocks/server";
import { FAILURE_COPY } from "./packs.generate";

function renderGenerate() {
  window.history.pushState({}, "", "/packs/generate");
  render(<App />);
}

// The composer's placeholder changes across phases (market words → refine… →
// Waiting… → Saving…), so query it by role to stay placeholder-agnostic.
function composerInput(): HTMLInputElement {
  return screen.getByRole("textbox") as HTMLInputElement;
}

async function findComposerInput(): Promise<HTMLInputElement> {
  return (await screen.findByRole("textbox")) as HTMLInputElement;
}

describe("Create a pack — chat scaffold + draft preview", () => {
  it("[WF-15] renders the empty state with intro copy, starter chips, and input", async () => {
    renderGenerate();

    expect(await screen.findByText(/Tell me what you'd like to practice/i)).toBeTruthy();
    expect(screen.getByText(/only use characters that live in the writing corpus/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Ordering at a restaurant" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Days, dates & the weekend" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "HSK-1 verbs I keep forgetting" })).toBeTruthy();
    expect(composerInput()).toBeTruthy();
  });

  it("[WF-15] sends a typed topic, shows in-flight state, then the draft preview", async () => {
    renderGenerate();

    const input = await findComposerInput();
    fireEvent.change(input, { target: { value: "Ordering at a restaurant" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    // In-flight: user bubble present, progress bubble shown, input disabled.
    expect(screen.getByText("Ordering at a restaurant")).toBeTruthy();
    expect(screen.getByText(/Drafting your pack/i)).toBeTruthy();
    expect(screen.getByText("This can take 30–60 seconds.")).toBeTruthy();
    // While generating, the placeholder flips to "Waiting for the draft…", so
    // query the input by role rather than its idle placeholder.
    expect((screen.getByRole("textbox") as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByPlaceholderText("Waiting for the draft…")).toBeTruthy();

    // Draft preview resolves (default MSW handler).
    expect(await screen.findByText(packDraft.title)).toBeTruthy();
    // characters[0]'s hanzi also renders in the glyph tile, so assert against a
    // later character whose hanzi appears only in the character grid.
    const character = packDraft.characters[1];
    expect(screen.getByText(character.hanzi)).toBeTruthy();
    expect(screen.getByText(character.pinyin)).toBeTruthy();
    expect(screen.getByText(character.meaning)).toBeTruthy();
    expect(screen.getByText(packDraft.sentences?.[0].hanzi ?? "")).toBeTruthy();
    // Coverage note surfaced verbatim from the fixture. The leading "Found …"
    // clause is bolded into its own span, so match on the paragraph's full text
    // content rather than a single direct text node.
    expect(
      screen.getByText(
        (_, node) => node?.tagName === "P" && node.textContent === packDraft.coverage_note,
      ),
    ).toBeTruthy();
    // Callout keeps its landmark role so a regression demoting it fails.
    expect(screen.getByRole("note", { name: /coverage/i })).toBeTruthy();
    // Input re-enabled once the draft lands.
    expect(composerInput().disabled).toBe(false);
  });

  it("[WF-15] submits a starter chip topic immediately", async () => {
    renderGenerate();

    fireEvent.click(await screen.findByRole("button", { name: "Ordering at a restaurant" }));

    // The chip text now appears as the user bubble (chips unmount with the
    // empty state), and the preview resolves.
    expect(screen.getByText("Ordering at a restaurant")).toBeTruthy();
    expect(await screen.findByText(packDraft.title)).toBeTruthy();
  });

  it("[WF-15] replays the client-held history from the first draft on a refinement turn", async () => {
    // Capture the request body of every draft POST so we can assert the second
    // turn replays exactly the history the first response handed back. This pins
    // issue #102's client-held-history contract against stale-closure regressions.
    const capturedHistories: unknown[] = [];
    server.use(
      http.post(`${API_V1_BASE}/generation/draft`, async ({ request }) => {
        const body = (await request.json()) as { topic: string; history?: unknown };
        capturedHistories.push(body.history);
        return HttpResponse.json({ draft: packDraft, history: generationHistory });
      }),
    );
    renderGenerate();

    // First turn: fresh topic, no history sent, response seeds the history.
    const input = await findComposerInput();
    fireEvent.change(input, { target: { value: "Ordering at a restaurant" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(packDraft.title)).toBeTruthy();

    // Second turn: refine the same conversation.
    const refined = await findComposerInput();
    fireEvent.change(refined, { target: { value: "Add some drinks" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(capturedHistories).toHaveLength(2));
    // First turn omits history entirely; the refinement replays the fixture the
    // first response returned, verbatim.
    expect(capturedHistories[0]).toBeUndefined();
    expect(capturedHistories[1]).toEqual(generationHistory);
  });

  it("[WF-15] surfaces a rate-limit error, keeps the conversation, and re-enables input", async () => {
    server.use(generationDraftFailure(429));
    renderGenerate();

    const input = await findComposerInput();
    fireEvent.change(input, { target: { value: "Market words" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText(FAILURE_COPY.rate_limited.headline)).toBeTruthy();
    expect(screen.getByText(FAILURE_COPY.rate_limited.body)).toBeTruthy();
    // Conversation retained: the user bubble is still present.
    expect(screen.getByText("Market words")).toBeTruthy();
    // Input re-enabled so the user can retry.
    expect(composerInput().disabled).toBe(false);
  });

  it("[WF-15] omits the coverage callout when the draft has no coverage note", async () => {
    server.use(
      http.post(`${API_V1_BASE}/generation/draft`, () =>
        HttpResponse.json({
          draft: { ...packDraft, coverage_note: null },
          history: generationHistory,
        }),
      ),
    );
    renderGenerate();

    const input = await findComposerInput();
    fireEvent.change(input, { target: { value: "Ordering at a restaurant" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText(packDraft.title)).toBeTruthy();
    expect(screen.queryByRole("note")).toBeNull();
  });
});

describe("Create a pack — refinement, save, and failure states", () => {
  async function reachFirstDraft() {
    renderGenerate();
    const input = await findComposerInput();
    fireEvent.change(input, { target: { value: "Ordering at a restaurant" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(packDraft.title)).toBeTruthy();
  }

  it("[WF-15] collapses the superseded draft to a chip and badges the new draft on a refinement turn", async () => {
    await reachFirstDraft();

    // After the first draft the composer becomes the refinement affordance.
    expect(screen.getByPlaceholderText(/refine/i)).toBeTruthy();

    const refine = await findComposerInput();
    fireEvent.change(refine, { target: { value: "Make it harder — add words for paying" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    // The new preview carries the DRAFT 2 badge.
    expect(await screen.findByText("Draft 2")).toBeTruthy();
    // Draft 1 collapses to a compact chip built from its captured fields.
    expect(
      screen.getByText(`Draft 1 · ${packDraft.title} · ${packDraft.characters.length} characters`),
    ).toBeTruthy();
  });

  it("[WF-15] saves the draft and navigates to the new pack's detail route", async () => {
    await reachFirstDraft();

    fireEvent.click(screen.getByRole("button", { name: "Save pack" }));

    // The MSW save handler mints a fresh pack UUID; the app lands on its detail route.
    await waitFor(() =>
      expect(window.location.pathname).toMatch(
        /^\/packs\/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/,
      ),
    );
  });

  it("[WF-15] keeps the draft and surfaces the server detail when a save is rejected", async () => {
    server.use(generationSaveFailure(422));
    await reachFirstDraft();

    fireEvent.click(screen.getByRole("button", { name: "Save pack" }));

    // The grounding backstop's missing-glyph message surfaces verbatim in the bubble.
    expect(await screen.findByText(/pack references characters missing from corpus/)).toBeTruthy();
    expect(screen.getByText(FAILURE_COPY.save_rejected.headline)).toBeTruthy();
    // The static guidance body is self-contained (finding 6) and renders too.
    expect(screen.getByText(FAILURE_COPY.save_rejected.body)).toBeTruthy();
    // S6-D affordance: the bubble offers a "Keep chatting" action (two now — one in
    // the draft preview, one in the error bubble).
    expect(screen.getAllByRole("button", { name: "Keep chatting" }).length).toBe(2);
    // Recoverable: the draft preview and the conversation stay right here.
    expect(screen.getByRole("heading", { name: packDraft.title })).toBeTruthy();
    expect(screen.getByText("Ordering at a restaurant")).toBeTruthy();
    // Save is clickable again.
    expect((screen.getByRole("button", { name: "Save pack" }) as HTMLButtonElement).disabled).toBe(
      false,
    );
  });

  it("[WF-15] does NOT offer Try again for a save-sourced network failure", async () => {
    // A network-level save failure maps to network_error — which IS retryable for a
    // draft turn — but its source is "save", so no "Try again" is offered: a fresh
    // draft turn is the wrong recovery here (the Save button is the retry).
    server.use(http.post(`${API_V1_BASE}/generation/packs`, () => HttpResponse.error()));
    await reachFirstDraft();

    fireEvent.click(screen.getByRole("button", { name: "Save pack" }));

    expect(await screen.findByText(FAILURE_COPY.network_error.headline)).toBeTruthy();
    // Source-gated: the draft-turn "Try again" must not appear on a save failure.
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
    // The draft preview stays, so Save remains the retry affordance.
    expect(screen.getByRole("button", { name: "Save pack" })).toBeTruthy();
  });

  it("[WF-15] offers Try again on a provider failure, recovers on the retry, and reuses the failed turn's user bubble", async () => {
    let calls = 0;
    server.use(
      http.post(`${API_V1_BASE}/generation/draft`, () => {
        calls += 1;
        if (calls === 1) {
          return HttpResponse.json(
            { error: { code: "bad_gateway", message: "upstream", request_id: "mock" } },
            { status: 502 },
          );
        }
        return HttpResponse.json({ draft: packDraft, history: generationHistory });
      }),
    );
    renderGenerate();

    const input = await findComposerInput();
    fireEvent.change(input, { target: { value: "Ordering at a restaurant" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    // First attempt fails with a first-class provider-failure bubble + Try again.
    expect(await screen.findByText(FAILURE_COPY.provider_failure.headline)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    // The retry resubmits the last topic and the second attempt renders the preview…
    expect(await screen.findByText(packDraft.title)).toBeTruthy();
    // …and did NOT append a second user bubble: the topic appears exactly once.
    expect(screen.getAllByText("Ordering at a restaurant")).toHaveLength(1);
  });

  it("[WF-15] locks the composer mid-save and fires no draft POST for a refinement submitted then", async () => {
    let draftCalls = 0;
    // A save that never resolves, so the UI stays in the saving phase for the
    // duration of the assertions.
    const savePending = new Promise<never>(() => {});
    server.use(
      http.post(`${API_V1_BASE}/generation/draft`, () => {
        draftCalls += 1;
        return HttpResponse.json({ draft: packDraft, history: generationHistory });
      }),
      http.post(`${API_V1_BASE}/generation/packs`, async () => {
        await savePending;
        return new HttpResponse(null, { status: 201 });
      }),
    );
    await reachFirstDraft();
    expect(draftCalls).toBe(1);

    fireEvent.click(screen.getByRole("button", { name: "Save pack" }));

    // Mid-save: composer disabled with the "Saving…" placeholder.
    const input = composerInput();
    await waitFor(() => expect(input.disabled).toBe(true));
    expect(screen.getByPlaceholderText("Saving…")).toBeTruthy();

    // Attempt a refinement while the save is in flight: the phase guard blocks it,
    // so no draft POST is made.
    fireEvent.change(input, { target: { value: "Add drinks" } });
    fireEvent.submit(input.closest("form") as HTMLFormElement);
    await waitFor(() => expect(screen.getByText("Ordering at a restaurant")).toBeTruthy());
    expect(draftCalls).toBe(1);
  });

  it("[WF-15] hides the model picker and sends no model for non-admins", async () => {
    // Default status handlers model the non-admin caller (`models: null`), so
    // this pins the "pixel-identical UI" contract: no picker chrome, and the
    // draft body carries no `model` key at all.
    let received: Record<string, unknown> | undefined;
    server.use(
      http.post(`${API_V1_BASE}/generation/draft`, async ({ request }) => {
        received = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ draft: packDraft, history: generationHistory });
      }),
    );
    renderGenerate();

    const input = await findComposerInput();
    expect(screen.queryByText("Model")).toBeNull();
    for (const option of chatModelOptions) {
      expect(screen.queryByRole("button", { name: option.label })).toBeNull();
    }

    fireEvent.change(input, { target: { value: "Ordering at a restaurant" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(packDraft.title)).toBeTruthy();

    expect(received).toBeDefined();
    expect(received && "model" in received).toBe(false);
  });

  it("[WF-15] shows the model picker to admins with every label and the default preselected", async () => {
    server.use(generationStatusAdmin());
    renderGenerate();

    // The server default (first entry) is preselected; the rest are not.
    const defaultChip = await screen.findByRole("button", { name: chatModelOptions[0].label });
    expect(defaultChip.getAttribute("aria-pressed")).toBe("true");
    for (const option of chatModelOptions.slice(1)) {
      const chip = screen.getByRole("button", { name: option.label });
      expect(chip.getAttribute("aria-pressed")).toBe("false");
    }
    expect(screen.getByText("Model")).toBeTruthy();
  });

  it("[WF-15] sends the selected model on a draft turn and omits it when untouched", async () => {
    const receivedBodies: Record<string, unknown>[] = [];
    server.use(
      generationStatusAdmin(),
      http.post(`${API_V1_BASE}/generation/draft`, async ({ request }) => {
        receivedBodies.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json({ draft: packDraft, history: generationHistory });
      }),
    );
    renderGenerate();

    // Untouched picker: the request stays model-free (server default).
    const input = await findComposerInput();
    await screen.findByRole("button", { name: chatModelOptions[0].label });
    fireEvent.change(input, { target: { value: "Ordering at a restaurant" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(packDraft.title)).toBeTruthy();
    expect("model" in receivedBodies[0]).toBe(false);

    // Pick a non-default model, then refine: the override rides the wire.
    fireEvent.click(screen.getByRole("button", { name: "Claude Sonnet 5" }));
    const refine = composerInput();
    fireEvent.change(refine, { target: { value: "Add some drinks" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(receivedBodies).toHaveLength(2));
    expect(receivedBodies[1].model).toBe("anthropic/claude-sonnet-5");
  });

  it("[WF-15] keeps the selected model in the body on a Try again retry", async () => {
    const receivedModels: unknown[] = [];
    let calls = 0;
    server.use(
      generationStatusAdmin(),
      http.post(`${API_V1_BASE}/generation/draft`, async ({ request }) => {
        calls += 1;
        const body = (await request.json()) as Record<string, unknown>;
        receivedModels.push(body.model);
        if (calls === 1) {
          return HttpResponse.json(
            { error: { code: "bad_gateway", message: "upstream", request_id: "mock" } },
            { status: 502 },
          );
        }
        return HttpResponse.json({ draft: packDraft, history: generationHistory });
      }),
    );
    renderGenerate();

    fireEvent.click(await screen.findByRole("button", { name: "MiniMax M3" }));
    const input = composerInput();
    fireEvent.change(input, { target: { value: "Ordering at a restaurant" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    // First attempt fails; the retry must replay the same override, not drop it.
    expect(await screen.findByText(FAILURE_COPY.provider_failure.headline)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText(packDraft.title)).toBeTruthy();
    expect(receivedModels).toEqual(["minimax/minimax-m3", "minimax/minimax-m3"]);
  });

  it("[WF-15] guards a double save — two rapid clicks fire exactly one POST", async () => {
    let saveCalls = 0;
    const savePending = new Promise<never>(() => {});
    server.use(
      http.post(`${API_V1_BASE}/generation/packs`, async () => {
        saveCalls += 1;
        await savePending;
        return new HttpResponse(null, { status: 201 });
      }),
    );
    await reachFirstDraft();

    const saveButton = screen.getByRole("button", { name: "Save pack" });
    fireEvent.click(saveButton);
    fireEvent.click(saveButton);

    await waitFor(() => expect(saveCalls).toBe(1));
    // Give any stray second request a chance to land, then confirm still one.
    expect(saveCalls).toBe(1);
  });
});
