import { describe, expect, it } from "vitest";
import type { PackDetail } from "./api";
import { collectPackStrokeCharacters } from "./strokes";

describe("collectPackStrokeCharacters", () => {
  it("includes sentence-only characters such as 很 from Greetings", () => {
    const pack = {
      characters: [
        { hanzi: "你", pinyin: "nǐ", meaning: "you" },
        { hanzi: "好", pinyin: "hǎo", meaning: "good" },
        { hanzi: "我", pinyin: "wǒ", meaning: "I, me" },
      ],
      sentences: [{ hanzi: "我很好", pinyin: "wǒ hěn hǎo", translation: "I am well" }],
    } satisfies Pick<PackDetail, "characters" | "sentences">;

    expect(collectPackStrokeCharacters(pack)).toEqual(["你", "好", "我", "很"]);
  });
});
