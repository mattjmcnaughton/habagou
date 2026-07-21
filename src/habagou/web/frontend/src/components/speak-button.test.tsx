import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SpeakButton } from "./speak-button";

class FakeUtterance {
  lang = "";
  rate = 1;
  voice: SpeechSynthesisVoice | null = null;
  onstart: (() => void) | null = null;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public text: string) {}
}

function installSpeech() {
  const speak = vi.fn();
  vi.stubGlobal("speechSynthesis", {
    speak,
    cancel: vi.fn(),
    getVoices: () => [{ lang: "zh-CN", name: "Mandarin" }] as SpeechSynthesisVoice[],
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  });
  vi.stubGlobal("SpeechSynthesisUtterance", FakeUtterance);
  return { speak };
}

describe("SpeakButton", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders nothing when speech is unsupported", () => {
    const { container } = render(<SpeakButton text="你好" />);
    expect(container.firstChild).toBeNull();
  });

  it("speaks the text with a Mandarin voice when tapped", () => {
    const { speak } = installSpeech();
    render(<SpeakButton text="你好" />);

    fireEvent.click(screen.getByRole("button", { name: "Play pronunciation of 你好" }));

    expect(speak).toHaveBeenCalledOnce();
    const utterance = speak.mock.calls[0][0] as FakeUtterance;
    expect(utterance.text).toBe("你好");
    expect(utterance.lang).toBe("zh-CN");
    expect(utterance.voice?.name).toBe("Mandarin");
  });
});
