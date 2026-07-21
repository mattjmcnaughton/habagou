import { useSpeak } from "@/lib/speech";

// A small speaker control that reads the given Chinese `text` aloud on tap.
// Renders nothing on devices without speech support so call sites can drop it in
// next to any hanzi without guarding. Stops click propagation so it can sit
// inside or beside other tappable rows.

type SpeakButtonProps = {
  text: string;
  label?: string;
  size?: "sm" | "md";
  className?: string;
};

export function SpeakButton({ text, label, size = "md", className }: SpeakButtonProps) {
  const { supported, speaking, speak } = useSpeak();
  if (!supported) {
    return null;
  }
  const dimensions = size === "sm" ? "h-8 w-8" : "h-10 w-10";
  const glyphSize = size === "sm" ? 16 : 18;
  return (
    <button
      aria-label={label ?? `Play pronunciation of ${text}`}
      className={[
        "inline-flex shrink-0 items-center justify-center rounded-full border border-white/10 bg-white/[0.03] transition-colors hover:bg-white/[0.07] hover:text-jade",
        speaking ? "text-jade" : "text-mist",
        dimensions,
        className ?? "",
      ].join(" ")}
      onClick={(event) => {
        event.stopPropagation();
        speak(text);
      }}
      type="button"
    >
      <SpeakerIcon size={glyphSize} />
    </button>
  );
}

function SpeakerIcon({ size }: { size: number }) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      height={size}
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={2}
      viewBox="0 0 24 24"
      width={size}
    >
      <path d="M11 5 6 9H2v6h4l5 4z" />
      <path d="M15.5 8.5a5 5 0 0 1 0 7" />
      <path d="M18.5 5.5a9 9 0 0 1 0 13" />
    </svg>
  );
}
