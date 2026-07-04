import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { QuizOptions } from "hanzi-writer";
import { createRef } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { server } from "../mocks/server";
import { TraceCanvas, type TraceCanvasHandle } from "./trace-canvas";
import { SCRIPTED_STROKE_COMPLETE_EVENT } from "./trace-events";

const { createWriter, writer } = vi.hoisted(() => {
  const writer = {
    cancelQuiz: vi.fn(),
    highlightStroke: vi.fn(),
    quiz: vi.fn(),
    setCharacter: vi.fn(),
    showCharacter: vi.fn(),
  };
  return {
    createWriter: vi.fn(),
    writer,
  };
});

vi.mock("hanzi-writer", () => ({
  default: {
    create: createWriter,
  },
}));

function renderTraceCanvas(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe("TraceCanvas", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    createWriter.mockReturnValue(writer);
    writer.cancelQuiz.mockReturnValue(undefined);
    writer.highlightStroke.mockResolvedValue(undefined);
    writer.quiz.mockResolvedValue(undefined);
    writer.setCharacter.mockResolvedValue(undefined);
    writer.showCharacter.mockResolvedValue(undefined);
  });

  it("wires Hanzi Writer options, stroke total, and quiz callbacks", async () => {
    const onComplete = vi.fn();
    const onStroke = vi.fn();
    const onTotal = vi.fn();

    renderTraceCanvas(
      <TraceCanvas
        hanzi="你"
        onComplete={onComplete}
        onStroke={onStroke}
        onTotal={onTotal}
        size={320}
      />,
    );

    expect(await screen.findByTestId("trace-canvas")).toBeTruthy();
    await waitFor(() => expect(createWriter).toHaveBeenCalled());

    const [_target, character, options] = createWriter.mock.calls[0];
    expect(character).toBe("你");
    expect(options).toMatchObject({
      width: 320,
      height: 320,
      padding: 16,
      showCharacter: false,
      showOutline: true,
      showHintAfterMisses: 3,
      strokeColor: "#9fd8c2",
      outlineColor: "rgba(232,236,238,0.16)",
      drawingColor: "#5fb89a",
      highlightColor: "#5fb89a",
    });
    expect(options.drawingWidth).toBeCloseTo(27.2);
    expect(onTotal).toHaveBeenCalledWith(1);
    expect(writer.quiz).toHaveBeenCalled();

    const quizOptions = writer.quiz.mock.calls[0][0] as Partial<QuizOptions>;
    quizOptions.onCorrectStroke?.({
      strokeNum: 0,
      character: "你",
      drawnPath: { pathString: "", points: [] },
      isBackwards: false,
      mistakesOnStroke: 0,
      totalMistakes: 0,
      strokesRemaining: 0,
    });
    quizOptions.onComplete?.({ character: "你", totalMistakes: 0 });

    expect(onStroke).toHaveBeenCalledWith(1);
    expect(writer.showCharacter).toHaveBeenCalledWith({ duration: 380 });
    expect(onComplete).toHaveBeenCalled();
  });

  it("exposes imperative hint and redo controls", async () => {
    const ref = createRef<TraceCanvasHandle>();

    renderTraceCanvas(<TraceCanvas hanzi="你" ref={ref} size={300} />);
    await waitFor(() => expect(writer.quiz).toHaveBeenCalled());

    act(() => {
      ref.current?.hint(2);
      ref.current?.redo();
    });

    expect(writer.highlightStroke).toHaveBeenCalledWith(2);
    expect(writer.cancelQuiz).toHaveBeenCalled();
    await waitFor(() => expect(writer.setCharacter).toHaveBeenCalledWith("你"));
    await waitFor(() => expect(writer.quiz).toHaveBeenCalledTimes(2));
  });

  it("keeps the writer alive when parent callbacks change", async () => {
    const onComplete = vi.fn();
    const onStroke = vi.fn();
    const onTotal = vi.fn();
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });

    const view = render(
      <QueryClientProvider client={queryClient}>
        <TraceCanvas
          hanzi="你"
          onComplete={vi.fn()}
          onStroke={vi.fn()}
          onTotal={vi.fn()}
          size={300}
        />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(createWriter).toHaveBeenCalledTimes(1));

    view.rerender(
      <QueryClientProvider client={queryClient}>
        <TraceCanvas
          hanzi="你"
          onComplete={onComplete}
          onStroke={onStroke}
          onTotal={onTotal}
          size={300}
        />
      </QueryClientProvider>,
    );

    expect(createWriter).toHaveBeenCalledTimes(1);

    const quizOptions = writer.quiz.mock.calls[0][0] as Partial<QuizOptions>;
    quizOptions.onCorrectStroke?.({
      strokeNum: 0,
      character: "你",
      drawnPath: { pathString: "", points: [] },
      isBackwards: false,
      mistakesOnStroke: 0,
      totalMistakes: 0,
      strokesRemaining: 0,
    });
    quizOptions.onComplete?.({ character: "你", totalMistakes: 0 });

    expect(onStroke).toHaveBeenCalledWith(1);
    expect(onComplete).toHaveBeenCalled();
  });

  it("exposes a deterministic scripted stroke completion hook", async () => {
    const onComplete = vi.fn();

    renderTraceCanvas(<TraceCanvas hanzi="你" onComplete={onComplete} size={300} />);
    const canvas = await screen.findByTestId("trace-canvas");
    await waitFor(() => expect(writer.quiz).toHaveBeenCalled());

    canvas.dispatchEvent(new CustomEvent(SCRIPTED_STROKE_COMPLETE_EVENT));

    expect(writer.showCharacter).toHaveBeenCalledWith({ duration: 380 });
    expect(onComplete).toHaveBeenCalled();
  });

  it("shows a recoverable stroke-data error", async () => {
    let failed = false;
    server.use(
      http.get("/api/v1/characters/:hanzi/strokes", () => {
        if (!failed) {
          failed = true;
          return HttpResponse.json(
            {
              error: {
                code: "database_unavailable",
                message: "database is unavailable",
                request_id: "req-strokes",
              },
            },
            { status: 503 },
          );
        }
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

    renderTraceCanvas(<TraceCanvas hanzi="你" size={300} />);

    expect((await screen.findByRole("alert")).textContent).toContain("Stroke data unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Retry stroke data" }));

    await waitFor(() => expect(createWriter).toHaveBeenCalled());
    expect(await screen.findByTestId("trace-canvas")).toBeTruthy();
  });
});
