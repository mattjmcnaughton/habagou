import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../app/app";
import { API_V1_BASE } from "../lib/api";
import { SCRIPTED_STROKE_COMPLETE_EVENT } from "../components/trace-canvas";
import { server } from "../mocks/server";

// Deterministic Hanzi Writer stand-in so the trace flow can be scripted without
// pointer input, mirroring trace-canvas.test.tsx.
const { createWriter, writer } = vi.hoisted(() => {
  const writer = {
    cancelQuiz: vi.fn(),
    highlightStroke: vi.fn(),
    quiz: vi.fn(),
    setCharacter: vi.fn(),
    showCharacter: vi.fn(),
  };
  return { createWriter: vi.fn(), writer };
});

vi.mock("hanzi-writer", () => ({
  default: { create: createWriter },
}));

// Item ids from the MSW path fixture (src/mocks/handlers.ts).
const TRACE_ITEM = "aaaaaaaa-0000-4000-8000-000000000003"; // Greetings trace: 你 好
const MATCH_ITEM = "aaaaaaaa-0000-4000-8000-000000000005"; // Greetings match: 你 好 我
const SENTENCE_ITEM = "aaaaaaaa-0000-4000-8000-000000000004"; // Greetings sentence: 你好 / Hello

function renderLesson(itemId: string) {
  window.history.pushState({}, "", `/lesson/${itemId}`);
  render(<App />);
}

async function traceCurrentCharacter(charNumber: number) {
  await waitFor(() => expect(createWriter).toHaveBeenCalledTimes(charNumber));
  const canvas = await screen.findByTestId("trace-canvas");
  act(() => {
    canvas.dispatchEvent(new CustomEvent(SCRIPTED_STROKE_COMPLETE_EVENT));
  });
}

describe("Lesson runner", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    createWriter.mockReturnValue(writer);
    writer.cancelQuiz.mockReturnValue(undefined);
    writer.highlightStroke.mockResolvedValue(undefined);
    writer.quiz.mockResolvedValue(undefined);
    writer.setCharacter.mockResolvedValue(undefined);
    writer.showCharacter.mockResolvedValue(undefined);
  });

  it("[WF-PATH] renders the trace activity with a back-to-Path link", async () => {
    renderLesson(TRACE_ITEM);

    expect(await screen.findByTestId("trace-canvas")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Path/ }).getAttribute("href")).toBe("/");
    expect(screen.getByText("1 / 2")).toBeTruthy();
    // The tab bar stays hidden on lesson routes (FE-1 rule).
    expect(screen.queryByRole("navigation", { name: "Primary" })).toBeNull();
  });

  it("[WF-PATH] renders the match activity for a match item", async () => {
    renderLesson(MATCH_ITEM);

    expect(await screen.findByRole("heading", { name: "Match characters" })).toBeTruthy();
    expect(screen.getByText("Tap a character, then its meaning.")).toBeTruthy();
    expect(screen.getByLabelText("Match board")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Path/ })).toBeTruthy();
  });

  it("[WF-PATH] renders the sentence activity for a sentence item", async () => {
    renderLesson(SENTENCE_ITEM);

    expect(await screen.findByRole("heading", { name: "Hello" })).toBeTruthy();
    expect(screen.getByText("nǐ hǎo")).toBeTruthy();
    expect(screen.getByText("1 / 1")).toBeTruthy();
  });

  it("[WF-PATH] shows a friendly not-found for an unknown item", async () => {
    renderLesson("ffffffff-0000-4000-8000-000000000000");

    expect(await screen.findByText("We could not find this lesson.")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Path/ }).getAttribute("href")).toBe("/");
  });

  it("[WF-PATH] posts the completion and shows the done screen", async () => {
    const completeCalls: { itemId: string; durationMs: unknown }[] = [];
    server.use(
      http.post(`${API_V1_BASE}/path/items/:itemId/complete`, async ({ params, request }) => {
        const body = (await request.json()) as { duration_ms: number };
        completeCalls.push({ itemId: String(params.itemId), durationMs: body.duration_ms });
        return HttpResponse.json(
          {
            daily: { completed: 3, target: 3 },
            streak: 12,
            item_id: String(params.itemId),
            next_item_id: null,
          },
          { status: 201 },
        );
      }),
    );

    renderLesson(TRACE_ITEM);

    await traceCurrentCharacter(1);
    fireEvent.click(await screen.findByRole("button", { name: "Next character" }));
    await traceCurrentCharacter(2);
    fireEvent.click(await screen.findByRole("button", { name: "Finish" }));

    expect(await screen.findByText("Lesson complete!")).toBeTruthy();
    expect(await screen.findByText("✓ Completion recorded")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Back to Path" }).getAttribute("href")).toBe("/");

    expect(completeCalls).toHaveLength(1);
    expect(completeCalls[0].itemId).toBe(TRACE_ITEM);
    expect(typeof completeCalls[0].durationMs).toBe("number");
  });

  it("[WF-PATH] treats a 409 (already completed) as done", async () => {
    server.use(
      http.post(`${API_V1_BASE}/path/items/:itemId/complete`, () =>
        HttpResponse.json(
          {
            error: {
              code: "already_completed",
              message: "path item already completed",
              request_id: "req-409",
            },
          },
          { status: 409 },
        ),
      ),
    );

    renderLesson(TRACE_ITEM);

    await traceCurrentCharacter(1);
    fireEvent.click(await screen.findByRole("button", { name: "Next character" }));
    await traceCurrentCharacter(2);
    fireEvent.click(await screen.findByRole("button", { name: "Finish" }));

    expect(await screen.findByText("Lesson complete!")).toBeTruthy();
    expect(await screen.findByText("✓ Completion recorded")).toBeTruthy();
  });
});
