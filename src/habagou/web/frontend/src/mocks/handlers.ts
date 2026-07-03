import { HttpResponse, http } from "msw";
import type { PackDetail, PackSummary, ProgressReset } from "../lib/api";

const API_V1 = "/api/v1";

export const packSummaries: PackSummary[] = [
  {
    id: "11111111-1111-4111-8111-111111111111",
    slug: "greetings",
    title: "Greetings",
    glyph: "你",
    color: "#c4633f",
    char_count: 5,
    sentence_count: 3,
    progress: {
      trace: { completed: false, completion_count: 0, best_duration_ms: null },
      match: { completed: false, completion_count: 0, best_duration_ms: null },
      sentence: { completed: false, completion_count: 0, best_duration_ms: null },
    },
  },
  {
    id: "22222222-2222-4222-8222-222222222222",
    slug: "numbers",
    title: "Numbers",
    glyph: "三",
    color: "#3f8a86",
    char_count: 5,
    sentence_count: 2,
    progress: {
      trace: { completed: true, completion_count: 1, best_duration_ms: 1500 },
      match: { completed: false, completion_count: 0, best_duration_ms: null },
      sentence: { completed: false, completion_count: 0, best_duration_ms: null },
    },
  },
];

const packDetails: Record<string, PackDetail> = {
  greetings: {
    ...packSummaries[0],
    characters: [
      { hanzi: "你", pinyin: "nǐ", meaning: "you" },
      { hanzi: "好", pinyin: "hǎo", meaning: "good" },
      { hanzi: "我", pinyin: "wǒ", meaning: "I, me" },
      { hanzi: "他", pinyin: "tā", meaning: "he, him" },
      { hanzi: "谢", pinyin: "xiè", meaning: "thanks" },
    ],
    sentences: [
      { hanzi: "你好", pinyin: "nǐ hǎo", translation: "Hello" },
      { hanzi: "我很好", pinyin: "wǒ hěn hǎo", translation: "I am well" },
      { hanzi: "谢谢你", pinyin: "xièxie nǐ", translation: "Thank you" },
    ],
  },
  numbers: {
    ...packSummaries[1],
    characters: [
      { hanzi: "一", pinyin: "yī", meaning: "one" },
      { hanzi: "二", pinyin: "èr", meaning: "two" },
      { hanzi: "三", pinyin: "sān", meaning: "three" },
      { hanzi: "四", pinyin: "sì", meaning: "four" },
      { hanzi: "五", pinyin: "wǔ", meaning: "five" },
    ],
    sentences: [
      { hanzi: "一二三", pinyin: "yī èr sān", translation: "One two three" },
      { hanzi: "三个人", pinyin: "sān ge rén", translation: "Three people" },
    ],
  },
};

export const handlers = [
  http.get(`${API_V1}/packs`, () => {
    return HttpResponse.json<PackSummary[]>(packSummaries);
  }),
  http.get(`${API_V1}/packs/:slug`, ({ params }) => {
    const slug = String(params.slug);
    const pack = packDetails[slug];
    if (!pack) {
      return HttpResponse.json({ detail: "pack not found" }, { status: 404 });
    }
    return HttpResponse.json<PackDetail>(pack);
  }),
  http.delete(`${API_V1}/progress/packs/:slug`, ({ params }) => {
    const slug = String(params.slug);
    const pack = packDetails[slug];
    if (!pack) {
      return HttpResponse.json({ detail: "pack not found" }, { status: 404 });
    }
    const reset: ProgressReset = {
      pack_slug: slug,
      deleted_count: 1,
      progress: {
        trace: { completed: false, completion_count: 0, best_duration_ms: null },
        match: { completed: false, completion_count: 0, best_duration_ms: null },
        sentence: { completed: false, completion_count: 0, best_duration_ms: null },
      },
    };
    return HttpResponse.json<ProgressReset>(reset);
  }),
];
