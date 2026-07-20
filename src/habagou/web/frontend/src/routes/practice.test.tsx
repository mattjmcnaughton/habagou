import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { App } from "../app/app";
import { API_V1_BASE } from "../lib/api";
import {
  chatModelOptions,
  practiceAsideTurn,
  practiceHistory,
  practiceOpeningTurn,
  practiceStatusAdmin,
  practiceTurnFailure,
} from "../mocks/handlers";
import { server } from "../mocks/server";
import { FAILURE_COPY } from "./practice";

function renderPractice() {
  window.history.pushState({}, "", "/practice");
  render(<App />);
}

// The composer's placeholder changes across phases, so query it by role.
function composerInput(): HTMLInputElement {
  return screen.getByRole("textbox") as HTMLInputElement;
}

async function findComposerInput(): Promise<HTMLInputElement> {
  return (await screen.findByRole("textbox")) as HTMLInputElement;
}

async function startConversation(topic = "Ordering food at a restaurant") {
  renderPractice();
  fireEvent.click(await screen.findByRole("button", { name: topic }));
  // The opening tutor turn resolves (default MSW handler).
  expect(await screen.findByText(practiceOpeningTurn.segments[0].hanzi)).toBeTruthy();
}

describe("Practice — topic picker and first turn", () => {
  it("[WF-16] renders the topic picker with intro copy, starter chips, and input", async () => {
    renderPractice();

    expect(await screen.findByText(/What would you like to talk about/i)).toBeTruthy();
    expect(screen.getByText(/English one tap away/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Ordering food at a restaurant" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Meeting someone new" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Asking for directions" })).toBeTruthy();
    expect(composerInput()).toBeTruthy();
  });

  it("[WF-16] submits a starter chip, shows the in-flight state, then the tutor's opener", async () => {
    renderPractice();

    fireEvent.click(await screen.findByRole("button", { name: "Meeting someone new" }));

    // In-flight: learner bubble present, thinking bubble shown, input disabled.
    expect(screen.getByText("Meeting someone new")).toBeTruthy();
    expect(screen.getByText(/Thinking of a reply/i)).toBeTruthy();
    expect((screen.getByRole("textbox") as HTMLInputElement).disabled).toBe(true);

    // The opening turn lands: hanzi and pinyin visible for every segment.
    for (const segment of practiceOpeningTurn.segments) {
      expect(await screen.findByText(segment.hanzi)).toBeTruthy();
      expect(screen.getByText(segment.pinyin)).toBeTruthy();
    }
    // Input re-enabled for the learner's reply.
    expect(composerInput().disabled).toBe(false);
  });

  it("[WF-16] shows the unavailable state when practice is not configured", async () => {
    server.use(
      http.get(`${API_V1_BASE}/practice/status`, () => HttpResponse.json({ enabled: false })),
    );
    renderPractice();

    expect(await screen.findByText(FAILURE_COPY.disabled.headline)).toBeTruthy();
    expect(screen.getByText(FAILURE_COPY.disabled.body)).toBeTruthy();
    // No topic picker and no composer: the flow can only 503.
    expect(screen.queryByRole("button", { name: "Ordering food at a restaurant" })).toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
  });
});

describe("Practice — tap-reveal translation and break glass", () => {
  it("[WF-16] hides each segment's English until tapped, per segment", async () => {
    await startConversation();

    const [first, second] = practiceOpeningTurn.segments;
    // English hidden by default for both segments.
    expect(screen.queryByText(first.english)).toBeNull();
    expect(screen.queryByText(second.english)).toBeNull();

    // Tapping one segment reveals only that segment's English…
    fireEvent.click(screen.getByRole("button", { name: new RegExp(first.hanzi) }));
    expect(screen.getByText(first.english)).toBeTruthy();
    expect(screen.queryByText(second.english)).toBeNull();

    // …and tapping again hides it.
    fireEvent.click(screen.getByRole("button", { name: new RegExp(first.hanzi) }));
    expect(screen.queryByText(first.english)).toBeNull();
  });

  it("[WF-16] renders the English aside as a distinct note alongside the segments", async () => {
    server.use(
      http.post(`${API_V1_BASE}/practice/turn`, () =>
        HttpResponse.json({ turn: practiceAsideTurn, history: practiceHistory }),
      ),
    );
    renderPractice();
    fireEvent.click(await screen.findByRole("button", { name: "Asking for directions" }));
    expect(await screen.findByText(practiceAsideTurn.segments[0].hanzi)).toBeTruthy();

    // The break-glass aside renders as its own landmark note…
    expect(screen.getByRole("note", { name: /English aside/i })).toBeTruthy();
    expect(screen.getByText(practiceAsideTurn.english_aside ?? "")).toBeTruthy();
    // …while the Chinese conversation continues in the same turn.
    expect(screen.getByText(practiceAsideTurn.segments[0].hanzi)).toBeTruthy();
  });
});

describe("Practice — follow-up turns, failures, and reset", () => {
  it("[WF-16] replays the client-held history from the first turn on a follow-up", async () => {
    const capturedHistories: unknown[] = [];
    server.use(
      http.post(`${API_V1_BASE}/practice/turn`, async ({ request }) => {
        const body = (await request.json()) as { message: string; history?: unknown };
        capturedHistories.push(body.history);
        return HttpResponse.json({ turn: practiceOpeningTurn, history: practiceHistory });
      }),
    );
    await startConversation();

    const input = await findComposerInput();
    fireEvent.change(input, { target: { value: "我要吃饭" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(capturedHistories).toHaveLength(2));
    // First turn omits history entirely; the follow-up replays the fixture the
    // first response returned, verbatim.
    expect(capturedHistories[0]).toBeUndefined();
    expect(capturedHistories[1]).toEqual(practiceHistory);
  });

  it("[WF-16] keeps earlier tutor turns in the transcript after a follow-up", async () => {
    await startConversation();

    const input = await findComposerInput();
    fireEvent.change(input, { target: { value: "我要吃饭" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    // Two tutor turns now render the same opener fixture: both stay visible.
    await waitFor(() =>
      expect(screen.getAllByText(practiceOpeningTurn.segments[0].hanzi)).toHaveLength(2),
    );
  });

  it("[WF-16] surfaces a rate-limit error, keeps the conversation, and re-enables input", async () => {
    server.use(practiceTurnFailure(429));
    renderPractice();

    fireEvent.click(await screen.findByRole("button", { name: "Meeting someone new" }));

    expect(await screen.findByText(FAILURE_COPY.rate_limited.headline)).toBeTruthy();
    expect(screen.getByText(FAILURE_COPY.rate_limited.body)).toBeTruthy();
    // Conversation retained: the learner bubble is still present.
    expect(screen.getByText("Meeting someone new")).toBeTruthy();
    // No Try again for a rate limit (no retry-after data to honor).
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
    expect(composerInput().disabled).toBe(false);
  });

  it("[WF-16] offers Try again on a provider failure and reuses the failed turn's bubble", async () => {
    let calls = 0;
    server.use(
      http.post(`${API_V1_BASE}/practice/turn`, () => {
        calls += 1;
        if (calls === 1) {
          return HttpResponse.json(
            { error: { code: "bad_gateway", message: "upstream", request_id: "mock" } },
            { status: 502 },
          );
        }
        return HttpResponse.json({ turn: practiceOpeningTurn, history: practiceHistory });
      }),
    );
    renderPractice();

    fireEvent.click(await screen.findByRole("button", { name: "Meeting someone new" }));

    expect(await screen.findByText(FAILURE_COPY.provider_failure.headline)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    // The retry resubmits the last message and the tutor turn renders…
    expect(await screen.findByText(practiceOpeningTurn.segments[0].hanzi)).toBeTruthy();
    // …without appending a second learner bubble.
    expect(screen.getAllByText("Meeting someone new")).toHaveLength(1);
    // The superseded failure bubble no longer offers Try again: clicking it
    // now would resubmit the latest message and duplicate the exchange.
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });

  it("[WF-16] retires an old failure's Try again once a newer message lands", async () => {
    let calls = 0;
    server.use(
      http.post(`${API_V1_BASE}/practice/turn`, () => {
        calls += 1;
        if (calls === 1) {
          return HttpResponse.json(
            { error: { code: "bad_gateway", message: "upstream", request_id: "mock" } },
            { status: 502 },
          );
        }
        return HttpResponse.json({ turn: practiceOpeningTurn, history: practiceHistory });
      }),
    );
    renderPractice();

    // First message fails; instead of retrying, the learner types a new one.
    fireEvent.click(await screen.findByRole("button", { name: "Meeting someone new" }));
    expect(await screen.findByText(FAILURE_COPY.provider_failure.headline)).toBeTruthy();
    const input = composerInput();
    fireEvent.change(input, { target: { value: "你好" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(practiceOpeningTurn.segments[0].hanzi)).toBeTruthy();

    // The failure bubble stays in the transcript, but its Try again is gone —
    // it would resubmit "你好" (the latest message), not the one that failed.
    expect(screen.getByText(FAILURE_COPY.provider_failure.headline)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });

  it("[WF-16] withholds the topic picker until the status probe resolves", async () => {
    // A never-resolving probe: the screen must fail closed (no picker,
    // disabled composer) rather than collect a message a disabled server
    // could only 503.
    server.use(http.get(`${API_V1_BASE}/practice/status`, () => new Promise<never>(() => {})));
    renderPractice();

    expect(await screen.findByRole("heading", { name: /Practice/ })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Ordering food at a restaurant" })).toBeNull();
    expect(composerInput().disabled).toBe(true);
  });

  it("[WF-16] hides the model picker and sends no model for non-admins", async () => {
    // Default status handlers model the non-admin caller (`models: null`), so
    // this pins the "pixel-identical UI" contract: no picker chrome, and the
    // turn body carries no `model` key at all.
    let received: Record<string, unknown> | undefined;
    server.use(
      http.post(`${API_V1_BASE}/practice/turn`, async ({ request }) => {
        received = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ turn: practiceOpeningTurn, history: practiceHistory });
      }),
    );
    renderPractice();

    const chip = await screen.findByRole("button", { name: "Ordering food at a restaurant" });
    // No model pill and no sheet chrome for a non-admin caller.
    expect(screen.queryByRole("button", { name: /Tutor model:/ })).toBeNull();
    for (const option of chatModelOptions) {
      expect(screen.queryByRole("button", { name: option.label })).toBeNull();
    }

    fireEvent.click(chip);
    expect(await screen.findByText(practiceOpeningTurn.segments[0].hanzi)).toBeTruthy();

    expect(received).toBeDefined();
    expect(received && "model" in received).toBe(false);
  });

  it("[WF-16] shows the model pill to admins and preselects the default in the sheet", async () => {
    server.use(practiceStatusAdmin());
    renderPractice();

    // The pill names the server default (first entry) before any interaction.
    const pill = await screen.findByRole("button", {
      name: `Tutor model: ${chatModelOptions[0].label}`,
    });
    // Options live in a sheet, hidden until the pill is tapped.
    expect(screen.queryByRole("button", { name: chatModelOptions[1].label })).toBeNull();

    fireEvent.click(pill);

    // The default option is preselected; the rest are not.
    const defaultOption = await screen.findByRole("button", { name: chatModelOptions[0].label });
    expect(defaultOption.getAttribute("aria-pressed")).toBe("true");
    for (const option of chatModelOptions.slice(1)) {
      const modelOption = screen.getByRole("button", { name: option.label });
      expect(modelOption.getAttribute("aria-pressed")).toBe("false");
    }
    expect(screen.getByRole("dialog", { name: /Choose tutor model/i })).toBeTruthy();
  });

  it("[WF-16] sends the selected model on a turn and omits it when untouched", async () => {
    const receivedBodies: Record<string, unknown>[] = [];
    server.use(
      practiceStatusAdmin(),
      http.post(`${API_V1_BASE}/practice/turn`, async ({ request }) => {
        receivedBodies.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json({ turn: practiceOpeningTurn, history: practiceHistory });
      }),
    );
    renderPractice();

    // Untouched picker: the request stays model-free (server default).
    fireEvent.click(await screen.findByRole("button", { name: "Meeting someone new" }));
    expect(await screen.findByText(practiceOpeningTurn.segments[0].hanzi)).toBeTruthy();
    expect("model" in receivedBodies[0]).toBe(false);

    // Open the sheet and pick a non-default model, then follow up: the override
    // rides the wire.
    fireEvent.click(screen.getByRole("button", { name: /Tutor model:/ }));
    fireEvent.click(screen.getByRole("button", { name: "Claude Sonnet 5" }));
    const input = composerInput();
    fireEvent.change(input, { target: { value: "我要吃饭" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(receivedBodies).toHaveLength(2));
    expect(receivedBodies[1].model).toBe("anthropic/claude-sonnet-5");
  });

  it("[WF-16] keeps the selected model in the body on a Try again retry", async () => {
    const receivedModels: unknown[] = [];
    let calls = 0;
    server.use(
      practiceStatusAdmin(),
      http.post(`${API_V1_BASE}/practice/turn`, async ({ request }) => {
        calls += 1;
        const body = (await request.json()) as Record<string, unknown>;
        receivedModels.push(body.model);
        if (calls === 1) {
          return HttpResponse.json(
            { error: { code: "bad_gateway", message: "upstream", request_id: "mock" } },
            { status: 502 },
          );
        }
        return HttpResponse.json({ turn: practiceOpeningTurn, history: practiceHistory });
      }),
    );
    renderPractice();

    // Open the sheet, choose the override, then start the conversation.
    fireEvent.click(await screen.findByRole("button", { name: /Tutor model:/ }));
    fireEvent.click(screen.getByRole("button", { name: "MiniMax M3" }));
    fireEvent.click(screen.getByRole("button", { name: "Meeting someone new" }));

    // First attempt fails; the retry must replay the same override, not drop it.
    expect(await screen.findByText(FAILURE_COPY.provider_failure.headline)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText(practiceOpeningTurn.segments[0].hanzi)).toBeTruthy();
    expect(receivedModels).toEqual(["minimax/minimax-m3", "minimax/minimax-m3"]);
  });

  it("[WF-16] New discards the conversation and returns to the topic picker", async () => {
    await startConversation();

    fireEvent.click(screen.getByRole("button", { name: "New" }));

    // Ephemeral by design: the transcript is gone, the picker is back.
    expect(await screen.findByText(/What would you like to talk about/i)).toBeTruthy();
    expect(screen.queryByText(practiceOpeningTurn.segments[0].hanzi)).toBeNull();
    expect(screen.queryByText("Ordering food at a restaurant")).toBeTruthy();
  });
});
