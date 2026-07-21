import { describe, expect, it } from "vitest";
import { isSpeechSupported, pickChineseVoice } from "./speech";

function voice(lang: string, name = lang): SpeechSynthesisVoice {
  return { lang, name } as SpeechSynthesisVoice;
}

describe("pickChineseVoice", () => {
  it("returns null when no Chinese voice is available", () => {
    expect(pickChineseVoice([voice("en-US"), voice("fr-FR")])).toBeNull();
    expect(pickChineseVoice([])).toBeNull();
  });

  it("prefers a zh-CN voice over other Chinese variants", () => {
    const picked = pickChineseVoice([voice("zh-TW"), voice("zh-CN", "Mandarin"), voice("zh-HK")]);
    expect(picked?.name).toBe("Mandarin");
  });

  it("matches zh-CN regardless of separator or case", () => {
    expect(pickChineseVoice([voice("zh_CN", "underscore")])?.name).toBe("underscore");
    expect(pickChineseVoice([voice("ZH-CN", "upper")])?.name).toBe("upper");
  });

  it("falls back to any Chinese voice when no zh-CN exists", () => {
    expect(pickChineseVoice([voice("en-US"), voice("zh-TW", "Taiwan")])?.name).toBe("Taiwan");
  });
});

describe("isSpeechSupported", () => {
  it("is false in the jsdom test environment (no speechSynthesis)", () => {
    expect(isSpeechSupported()).toBe(false);
  });
});
