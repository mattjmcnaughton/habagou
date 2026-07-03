import { useQuery } from "@tanstack/react-query";
import HanziWriter from "hanzi-writer";
import type { QuizOptions } from "hanzi-writer";
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef } from "react";
import { characterStrokesQueryOptions } from "../lib/strokes";
import { SCRIPTED_STROKE_COMPLETE_EVENT } from "./trace-events";

export type TraceCanvasHandle = {
  hint(strokeNum?: number): void;
  redo(): void;
};

type HanziWriterInstance = ReturnType<typeof HanziWriter.create>;

type TraceCanvasProps = {
  hanzi: string;
  size: number;
  onComplete?: () => void;
  onStroke?: (strokeNumber: number) => void;
  onTotal?: (strokeCount: number) => void;
};

const WRITER_PADDING = 16;
const COMPLETE_REVEAL_MS = 380;

export const TraceCanvas = forwardRef<TraceCanvasHandle, TraceCanvasProps>(function TraceCanvas(
  { hanzi, onComplete, onStroke, onTotal, size },
  ref,
) {
  const targetRef = useRef<HTMLDivElement | null>(null);
  const writerRef = useRef<HanziWriterInstance | null>(null);
  const quizOptionsRef = useRef<Partial<QuizOptions> | null>(null);
  const strokeData = useQuery(characterStrokesQueryOptions(hanzi));

  const writerOptions = useMemo(
    () => ({
      width: size,
      height: size,
      padding: WRITER_PADDING,
      showCharacter: false,
      showOutline: true,
      showHintAfterMisses: 3,
      strokeColor: "#9fd8c2",
      outlineColor: "rgba(232,236,238,0.16)",
      drawingColor: "#5fb89a",
      highlightColor: "#5fb89a",
      drawingWidth: size * 0.085,
      charDataLoader: (
        _character: string,
        onLoad: (data: NonNullable<typeof strokeData.data>) => void,
      ) => {
        if (strokeData.data) {
          onLoad(strokeData.data);
        }
      },
    }),
    [size, strokeData.data],
  );

  useImperativeHandle(ref, () => ({
    hint(strokeNum = 0) {
      void writerRef.current?.highlightStroke(strokeNum);
    },
    redo() {
      if (!writerRef.current || !quizOptionsRef.current) {
        return;
      }
      writerRef.current.cancelQuiz();
      void writerRef.current
        .setCharacter(hanzi)
        .then(() => writerRef.current?.quiz(quizOptionsRef.current ?? {}));
    },
  }));

  useEffect(() => {
    const target = targetRef.current;
    if (!target || !strokeData.data) {
      return;
    }

    target.innerHTML = "";
    const writer = HanziWriter.create(target, hanzi, writerOptions);
    writerRef.current = writer;
    onTotal?.(strokeData.data.strokes.length);

    const completeStroke = () => {
      void writer.showCharacter({ duration: COMPLETE_REVEAL_MS });
      onComplete?.();
    };
    const quizOptions: Partial<QuizOptions> = {
      onCorrectStroke: (stroke) => onStroke?.(stroke.strokeNum + 1),
      onComplete: completeStroke,
    };
    quizOptionsRef.current = quizOptions;
    target.addEventListener(SCRIPTED_STROKE_COMPLETE_EVENT, completeStroke);
    void writer.quiz(quizOptions);

    return () => {
      target.removeEventListener(SCRIPTED_STROKE_COMPLETE_EVENT, completeStroke);
      writer.cancelQuiz();
      if (writerRef.current === writer) {
        writerRef.current = null;
      }
      target.innerHTML = "";
    };
  }, [hanzi, onComplete, onStroke, onTotal, strokeData.data, writerOptions]);

  if (strokeData.isError) {
    return (
      <div className="flex aspect-square w-full items-center justify-center rounded-lg border border-clay/40 bg-panel text-sm text-clay">
        Stroke data unavailable for <span className="ml-1 font-hanzi">{hanzi}</span>
      </div>
    );
  }

  return (
    <div
      aria-label={`Trace ${hanzi}`}
      className="flex aspect-square w-full items-center justify-center"
      data-hanzi={hanzi}
      data-testid="trace-canvas"
      ref={targetRef}
      role="img"
      style={{ maxHeight: size, maxWidth: size }}
    />
  );
});
