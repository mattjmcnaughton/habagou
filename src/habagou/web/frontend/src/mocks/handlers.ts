import { HttpResponse, http } from "msw";
import type {
  AuthSession,
  CompletePathItemResponse,
  CompletionResponse,
  PackDetail,
  PackSummary,
  PathItem,
  PathResponse,
  ProgressReset,
  ProgressSummary,
} from "../lib/api";

const API_V1 = "/api/v1";

export const authenticatedSession: AuthSession = {
  authenticated: true,
  provider: "keycloak",
  user: {
    id: "99999999-9999-4999-8999-999999999999",
    username: "dev",
    display_name: "Dev User",
    email: "dev@example.com",
  },
};

export const packSummaries: PackSummary[] = [
  {
    id: "11111111-1111-4111-8111-111111111111",
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
  [packSummaries[0].id]: {
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
  [packSummaries[1].id]: {
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

function mockProgressSummary(): ProgressSummary {
  const today = new Date();
  return {
    current_streak: 12,
    best_streak: 21,
    daily_goal: { completed: 2, target: 3 },
    activity: Array.from({ length: 45 }, (_, index) => {
      const date = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 44 + index);
      const count = [0, 1, 2, 3, 3, 0, 2][index % 7];
      return {
        date: [
          date.getFullYear(),
          String(date.getMonth() + 1).padStart(2, "0"),
          String(date.getDate()).padStart(2, "0"),
        ].join("-"),
        count,
        level: Math.min(count, 3),
      };
    }),
    next_milestone: {
      target_days: 14,
      days_remaining: 2,
      progress_pct: 86,
    },
    characters_traced: 7,
    packs_completed: 1,
    packs_total: 4,
  };
}

const GREETINGS_PACK: PathItem["pack"] = {
  title: "Greetings",
  glyph: "你",
  color: "#c4633f",
};

const NUMBERS_PACK: PathItem["pack"] = {
  title: "Numbers",
  glyph: "三",
  color: "#3f8a86",
};

// ~8 items across 2 packs: a done/current/locked mix, one review item, and a
// unit label on the first item.
const pathItems: PathItem[] = [
  {
    id: "aaaaaaaa-0000-4000-8000-000000000001",
    position: 1,
    activity: "trace",
    kind: "new",
    state: "done",
    unit_label: "UNIT 1 · WARMING UP",
    pack: NUMBERS_PACK,
    content: {
      trace: {
        chars: [
          { hanzi: "一", pinyin: "yī", meaning: "one" },
          { hanzi: "二", pinyin: "èr", meaning: "two" },
          { hanzi: "三", pinyin: "sān", meaning: "three" },
        ],
      },
    },
  },
  {
    id: "aaaaaaaa-0000-4000-8000-000000000002",
    position: 2,
    activity: "match",
    kind: "new",
    state: "done",
    unit_label: null,
    pack: NUMBERS_PACK,
    content: {
      match: {
        pairs: [
          { hanzi: "一", pinyin: "yī", meaning: "one" },
          { hanzi: "二", pinyin: "èr", meaning: "two" },
          { hanzi: "三", pinyin: "sān", meaning: "three" },
          { hanzi: "四", pinyin: "sì", meaning: "four" },
        ],
      },
    },
  },
  {
    id: "aaaaaaaa-0000-4000-8000-000000000003",
    position: 3,
    activity: "trace",
    kind: "new",
    state: "current",
    unit_label: null,
    pack: GREETINGS_PACK,
    content: {
      trace: {
        chars: [
          { hanzi: "你", pinyin: "nǐ", meaning: "you" },
          { hanzi: "好", pinyin: "hǎo", meaning: "good" },
        ],
      },
    },
  },
  {
    id: "aaaaaaaa-0000-4000-8000-000000000004",
    position: 4,
    activity: "sentence",
    kind: "new",
    state: "locked",
    unit_label: "UNIT 2 · GREETINGS",
    pack: GREETINGS_PACK,
    content: {
      sentence: { hanzi: "你好", pinyin: "nǐ hǎo", translation: "Hello" },
    },
  },
  {
    id: "aaaaaaaa-0000-4000-8000-000000000005",
    position: 5,
    activity: "match",
    kind: "new",
    state: "locked",
    unit_label: null,
    pack: GREETINGS_PACK,
    content: {
      match: {
        pairs: [
          { hanzi: "你", pinyin: "nǐ", meaning: "you" },
          { hanzi: "好", pinyin: "hǎo", meaning: "good" },
          { hanzi: "我", pinyin: "wǒ", meaning: "I, me" },
        ],
      },
    },
  },
  {
    id: "aaaaaaaa-0000-4000-8000-000000000006",
    position: 6,
    activity: "trace",
    kind: "review",
    state: "locked",
    unit_label: null,
    pack: NUMBERS_PACK,
    content: {
      trace: {
        chars: [
          { hanzi: "四", pinyin: "sì", meaning: "four" },
          { hanzi: "五", pinyin: "wǔ", meaning: "five" },
        ],
      },
    },
  },
  {
    id: "aaaaaaaa-0000-4000-8000-000000000007",
    position: 7,
    activity: "sentence",
    kind: "new",
    state: "locked",
    unit_label: null,
    pack: NUMBERS_PACK,
    content: {
      sentence: { hanzi: "一二三", pinyin: "yī èr sān", translation: "One two three" },
    },
  },
  {
    id: "aaaaaaaa-0000-4000-8000-000000000008",
    position: 8,
    activity: "match",
    kind: "new",
    state: "locked",
    unit_label: null,
    pack: GREETINGS_PACK,
    content: {
      match: {
        pairs: [
          { hanzi: "他", pinyin: "tā", meaning: "he, him" },
          { hanzi: "谢", pinyin: "xiè", meaning: "thanks" },
          { hanzi: "我", pinyin: "wǒ", meaning: "I, me" },
        ],
      },
    },
  },
];

const pathDaily = { completed: 2, target: 3 };
const completedPathItemIds = new Set<string>();

function pathPage(cursor: number, limit: number): PathResponse {
  const start = Number.isFinite(cursor) ? cursor : 0;
  const slice = pathItems.slice(start, start + limit);
  const nextIndex = start + slice.length;
  const next_cursor = nextIndex < pathItems.length ? nextIndex : null;
  return {
    items: slice,
    next_cursor,
    daily: { ...pathDaily },
    streak: 12,
    due: { new: 1, review: 2 },
  };
}

export const handlers = [
  http.get(`${API_V1}/auth/session`, () => {
    return HttpResponse.json<AuthSession>(authenticatedSession);
  }),
  http.post("/auth/logout", () => {
    return new HttpResponse(null, { status: 204 });
  }),
  http.get(`${API_V1}/packs`, () => {
    return HttpResponse.json<PackSummary[]>(packSummaries);
  }),
  http.get(`${API_V1}/progress/summary`, () => {
    return HttpResponse.json<ProgressSummary>(mockProgressSummary());
  }),
  http.get(`${API_V1}/packs/:packId`, ({ params }) => {
    const packId = String(params.packId);
    const pack = packDetails[packId];
    if (!pack) {
      return HttpResponse.json(
        { error: { code: "not_found", message: "pack not found", request_id: "mock-request" } },
        { status: 404 },
      );
    }
    return HttpResponse.json<PackDetail>(pack);
  }),
  http.get(`${API_V1}/characters/:hanzi/strokes`, () => {
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
  http.post(`${API_V1}/progress/completions`, async ({ request }) => {
    const completion = (await request.json()) as {
      activity: "match" | "sentence" | "trace";
      duration_ms: number;
      pack_id: string;
    };
    const summary = packSummaries.find((item) => item.id === completion.pack_id);
    const pack = summary ? packDetails[summary.id] : undefined;
    if (!summary || !pack) {
      return HttpResponse.json(
        { error: { code: "not_found", message: "pack not found", request_id: "mock-request" } },
        { status: 404 },
      );
    }
    const progress = {
      ...pack.progress,
      [completion.activity]: {
        completed: true,
        completion_count: pack.progress[completion.activity].completion_count + 1,
        best_duration_ms: completion.duration_ms,
      },
    };
    pack.progress = progress;
    summary.progress = progress;
    const response: CompletionResponse = {
      activity: completion.activity,
      duration_ms: completion.duration_ms,
      progress,
    };
    return HttpResponse.json<CompletionResponse>(response);
  }),
  http.get(`${API_V1}/path`, ({ request }) => {
    const url = new URL(request.url);
    const cursor = Number(url.searchParams.get("cursor") ?? "0");
    const rawLimit = Number(url.searchParams.get("limit") ?? "50");
    const limit = Math.min(Number.isFinite(rawLimit) ? rawLimit : 50, 50);
    return HttpResponse.json<PathResponse>(pathPage(cursor, limit));
  }),
  http.post(`${API_V1}/path/items/:itemId/complete`, ({ params }) => {
    const itemId = String(params.itemId);
    const item = pathItems.find((entry) => entry.id === itemId);
    if (!item) {
      return HttpResponse.json(
        {
          error: { code: "not_found", message: "path item not found", request_id: "mock-request" },
        },
        { status: 404 },
      );
    }
    if (completedPathItemIds.has(itemId)) {
      return HttpResponse.json(
        {
          error: {
            code: "already_completed",
            message: "path item already completed",
            request_id: "mock-request",
          },
        },
        { status: 409 },
      );
    }
    completedPathItemIds.add(itemId);
    pathDaily.completed = Math.min(pathDaily.completed + 1, pathDaily.target);
    const next = pathItems.find((entry) => entry.position === item.position + 1);
    const response: CompletePathItemResponse = {
      daily: { ...pathDaily },
      streak: 12,
      item_id: itemId,
      next_item_id: next?.id ?? null,
    };
    return HttpResponse.json<CompletePathItemResponse>(response, { status: 201 });
  }),
  http.delete(`${API_V1}/progress/packs/:packId`, ({ params }) => {
    const packId = String(params.packId);
    const pack = packDetails[packId];
    if (!pack) {
      return HttpResponse.json(
        { error: { code: "not_found", message: "pack not found", request_id: "mock-request" } },
        { status: 404 },
      );
    }
    const reset: ProgressReset = {
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
