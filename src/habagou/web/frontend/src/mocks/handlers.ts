import { HttpResponse, http } from "msw";
import type {
  AuthSession,
  ChatModelOption,
  CompletePathItemResponse,
  CompletionResponse,
  GenerationDraftResponse,
  GenerationStatus,
  Library,
  PackDetail,
  PackDraft,
  PackSummary,
  PathItem,
  PathResponse,
  PracticeStatus,
  PracticeTurn,
  PracticeTurnResponse,
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
    // The default mock session is a non-admin, matching the null model-picker
    // fields the default status handlers return.
    is_admin: false,
    // No flags are registered in code yet, so the resolved map is empty.
    feature_flags: {},
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
    // Curated global pack: not owned by the signed-in user, so undeletable.
    owned: false,
    // Starter packs are enabled for a fresh user by default.
    starter: true,
    enabled: true,
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
    // Curated global pack: not owned by the signed-in user, so undeletable.
    owned: false,
    // Starter packs are enabled for a fresh user by default.
    starter: true,
    enabled: true,
    progress: {
      trace: { completed: true, completion_count: 1, best_duration_ms: 1500 },
      match: { completed: false, completion_count: 0, best_duration_ms: null },
      sentence: { completed: false, completion_count: 0, best_duration_ms: null },
    },
  },
  {
    id: "44444444-4444-4444-8444-444444444444",
    title: "Fruit",
    glyph: "果",
    color: "#7a8a3f",
    char_count: 6,
    sentence_count: 2,
    owned: false,
    // Library pack a fresh user has not enabled: hidden from the bench until
    // the enablement PUT flips it, mirroring the real API.
    starter: false,
    enabled: false,
    progress: {
      trace: { completed: false, completion_count: 0, best_duration_ms: null },
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
  [packSummaries[2].id]: {
    ...packSummaries[2],
    characters: [
      { hanzi: "果", pinyin: "guǒ", meaning: "fruit" },
      { hanzi: "苹", pinyin: "píng", meaning: "apple (píngguǒ)" },
      { hanzi: "香", pinyin: "xiāng", meaning: "fragrant" },
      { hanzi: "蕉", pinyin: "jiāo", meaning: "banana (xiāngjiāo)" },
      { hanzi: "西", pinyin: "xī", meaning: "west" },
      { hanzi: "瓜", pinyin: "guā", meaning: "melon" },
    ],
    sentences: [
      { hanzi: "我吃苹果", pinyin: "wǒ chī píngguǒ", translation: "I eat apples" },
      { hanzi: "西瓜很大", pinyin: "xīguā hěn dà", translation: "The watermelon is big" },
    ],
  },
};

// The curated library catalog (pack-library feature): global packs grouped by
// category. The Essentials entries reuse the bench fixtures' ids so enabling /
// disabling in the library is visible on the bench, and Fruit is the
// disabled-by-default, non-starter pack tests toggle (its bench summary and
// detail fixtures exist too, so enabling it surfaces it on the bench exactly
// like the real API). Mutable on purpose: the PUT enablement handler below
// flips `enabled` so tests can assert against refetched state; tests that
// toggle should reset what they touched.
export const libraryCategories: Library["categories"] = [
  {
    slug: "essentials",
    title: "Essentials",
    packs: [
      {
        id: packSummaries[0].id,
        title: "Greetings",
        glyph: "你",
        color: "#c4633f",
        description: "First words for meeting people.",
        char_count: 5,
        sentence_count: 3,
        starter: true,
        enabled: true,
      },
      {
        id: packSummaries[1].id,
        title: "Numbers",
        glyph: "三",
        color: "#3f8a86",
        description: "Count from one to five.",
        char_count: 5,
        sentence_count: 2,
        starter: true,
        enabled: true,
      },
    ],
  },
  {
    slug: "food-drink",
    title: "Food & Drink",
    packs: [
      {
        id: packSummaries[2].id,
        title: "Fruit",
        glyph: "果",
        color: "#7a8a3f",
        description: "Name the fruit on the market stall.",
        char_count: 6,
        sentence_count: 2,
        starter: false,
        enabled: false,
      },
    ],
  },
];

// Keep the library, bench summary, and detail fixtures agreeing on a pack's
// enablement. Exported so tests that flip a pack can restore the default.
export function setMockPackEnabled(packId: string, enabled: boolean): void {
  for (const category of libraryCategories) {
    for (const pack of category.packs) {
      if (pack.id === packId) {
        pack.enabled = enabled;
      }
    }
  }
  const summary = packSummaries.find((pack) => pack.id === packId);
  if (summary) {
    summary.enabled = enabled;
  }
  const detail = packDetails[packId];
  if (detail) {
    detail.enabled = enabled;
  }
}

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

// Agent pack generation (issue #102). Status gates the entry point; a draft
// turn returns a PackDraft plus opaque conversation history the client replays.
// A coherent restaurant-themed draft matching the mockup. The coverage_note is
// an honest shortfall note in the agent's canonical "found N of M" shape (see
// services/pack_generation.py's system prompt) so preview tests can assert the
// gap is surfaced rather than hidden.
export const packDraft: PackDraft = {
  title: "At the Restaurant",
  characters: [
    { hanzi: "点", pinyin: "diǎn", meaning: "to order" },
    { hanzi: "菜", pinyin: "cài", meaning: "dish, vegetable" },
    { hanzi: "饭", pinyin: "fàn", meaning: "rice, meal" },
    { hanzi: "要", pinyin: "yào", meaning: "to want" },
    { hanzi: "吃", pinyin: "chī", meaning: "to eat" },
    { hanzi: "喝", pinyin: "hē", meaning: "to drink" },
  ],
  sentences: [
    { hanzi: "我要点菜", pinyin: "wǒ yào diǎn cài", translation: "I want to order food" },
    { hanzi: "我要吃饭", pinyin: "wǒ yào chī fàn", translation: "I want to eat" },
  ],
  coverage_note:
    "Found 6 of 8 requested words; 菜单 (menu) and 服务员 (waiter) are multi-character words that aren't in the corpus yet.",
};

// Opaque, client-held message history echoed back from a draft turn.
export const generationHistory: unknown[] = [
  { role: "user", content: "restaurant" },
  { role: "assistant", content: "drafted a restaurant pack" },
];

function savedPackFromDraft(draft: PackDraft): PackDetail {
  return {
    id: crypto.randomUUID(),
    title: draft.title,
    glyph: draft.characters[0]?.hanzi ?? "字",
    color: "#c4633f",
    char_count: draft.characters.length,
    sentence_count: draft.sentences?.length ?? 0,
    // Freshly generated packs are always owned by their creator, never part of
    // the curated starter set, and always enabled.
    owned: true,
    starter: false,
    enabled: true,
    progress: {
      trace: { completed: false, completion_count: 0, best_duration_ms: null },
      match: { completed: false, completion_count: 0, best_duration_ms: null },
      sentence: { completed: false, completion_count: 0, best_duration_ms: null },
    },
    characters: draft.characters.map((character) => ({
      hanzi: character.hanzi,
      pinyin: character.pinyin,
      meaning: character.meaning,
    })),
    sentences: (draft.sentences ?? []).map((sentence) => ({
      hanzi: sentence.hanzi,
      pinyin: sentence.pinyin,
      translation: sentence.translation,
    })),
  };
}

// Conversational practice (WF-16). Status gates the screen; a turn returns a
// structured PracticeTurn (per-sentence hanzi/pinyin/English segments) plus
// opaque conversation history the client replays on the next turn.
export const practiceOpeningTurn: PracticeTurn = {
  segments: [
    { hanzi: "你好", pinyin: "nǐ hǎo", english: "Hello!" },
    { hanzi: "你想吃什么", pinyin: "nǐ xiǎng chī shénme", english: "What do you want to eat?" },
  ],
  english_aside: null,
};

export const practiceAsideTurn: PracticeTurn = {
  segments: [{ hanzi: "我们继续吧", pinyin: "wǒmen jìxù ba", english: "Let's continue!" }],
  english_aside: "它 means 'it' — it's used for things, not people.",
};

// Opaque, client-held message history echoed back from a practice turn.
export const practiceHistory: unknown[] = [
  { role: "user", content: "ordering food" },
  { role: "assistant", content: "opened the conversation" },
];

// The admin model picker's allowlist (ADM-04): server default first, matching
// the order the status endpoints return. The default handlers below return
// `models: null` — the server's shape for non-admin callers — so tests opt into
// the admin view via `server.use(generationStatusAdmin())` / `practiceStatusAdmin()`.
export const chatModelOptions: ChatModelOption[] = [
  { id: "openai/gpt-5.6-terra", label: "GPT-5.6 Terra" },
  { id: "anthropic/claude-sonnet-5", label: "Claude Sonnet 5" },
  { id: "minimax/minimax-m3", label: "MiniMax M3" },
];

// Admin-variant status handlers for tests to install via `server.use(...)`:
// only admin callers receive the selectable model list (default first).
export function generationStatusAdmin() {
  return http.get(`${API_V1}/generation/status`, () =>
    HttpResponse.json<GenerationStatus>({
      enabled: true,
      models: chatModelOptions,
      default_model: chatModelOptions[0].id,
    }),
  );
}

export function practiceStatusAdmin() {
  return http.get(`${API_V1}/practice/status`, () =>
    HttpResponse.json<PracticeStatus>({
      enabled: true,
      models: chatModelOptions,
      default_model: chatModelOptions[0].id,
    }),
  );
}

// Mirror app.py's `_http_error_code`: the real server derives the envelope
// `code` from the HTTP status, so mock failures must do the same to stay honest.
function httpErrorCode(status: number): string {
  const codes: Record<number, string> = {
    401: "unauthenticated",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
    502: "bad_gateway",
    503: "service_unavailable",
  };
  return codes[status] ?? `http_${status}`;
}

// Error-variant handlers for tests to install via `server.use(...)`. `code`
// defaults to the status-derived code the real server would emit; pass an
// override only when a test needs a specific (honest) code.
export function generationDraftFailure(status: number, code = httpErrorCode(status)) {
  return http.post(`${API_V1}/generation/draft`, () =>
    HttpResponse.json(
      { error: { code, message: `generation failed (${status})`, request_id: "mock-request" } },
      { status },
    ),
  );
}

// Pack-deletion error variant for tests to install via `server.use(...)`. Use
// 403 (curated/foreign pack) or 404 (nonexistent/foreign pack); `code` defaults
// to the status-derived code the real server would emit.
export function packDeleteFailure(status: number, code = httpErrorCode(status)) {
  return http.delete(`${API_V1}/packs/:packId`, () =>
    HttpResponse.json(
      {
        error: {
          code,
          message: `pack could not be deleted (${status})`,
          request_id: "mock-request",
        },
      },
      { status },
    ),
  );
}

export function generationSaveFailure(status: number, code = httpErrorCode(status)) {
  return http.post(`${API_V1}/generation/packs`, () =>
    HttpResponse.json(
      {
        error: {
          code,
          // The real save-rejection is HTTPException(detail=str(exc)) with no
          // `details`: the offending glyph list lands in `message`.
          message: "pack references characters missing from corpus: 𡘙",
          request_id: "mock-request",
        },
      },
      { status },
    ),
  );
}

export function practiceTurnFailure(status: number, code = httpErrorCode(status)) {
  return http.post(`${API_V1}/practice/turn`, () =>
    HttpResponse.json(
      { error: { code, message: `practice failed (${status})`, request_id: "mock-request" } },
      { status },
    ),
  );
}

export const handlers = [
  http.get(`${API_V1}/auth/session`, () => {
    return HttpResponse.json<AuthSession>(authenticatedSession);
  }),
  http.post("/auth/logout", () => {
    return new HttpResponse(null, { status: 204 });
  }),
  http.get(`${API_V1}/packs`, () => {
    // The bench lists only owned packs plus enabled global packs.
    return HttpResponse.json<PackSummary[]>(
      packSummaries.filter((pack) => pack.owned || pack.enabled),
    );
  }),
  http.get(`${API_V1}/library`, () => {
    return HttpResponse.json<Library>({ categories: libraryCategories });
  }),
  http.put(`${API_V1}/packs/:packId/enabled`, async ({ params, request }) => {
    const packId = String(params.packId);
    const body = (await request.json()) as { enabled: boolean };
    const known = libraryCategories.some((category) =>
      category.packs.some((pack) => pack.id === packId),
    );
    if (!known) {
      return HttpResponse.json(
        { error: { code: "not_found", message: "pack not found", request_id: "mock-request" } },
        { status: 404 },
      );
    }
    // Mutate the mock library (and mirrored bench/detail fixtures) so
    // invalidation-driven refetches observe the flip.
    setMockPackEnabled(packId, body.enabled);
    return new HttpResponse(null, { status: 204 });
  }),
  // Both status defaults model the non-admin caller: `models`/`default_model`
  // are explicitly null (the server's shape), so the model picker stays hidden
  // unless a test installs the admin variants above.
  http.get(`${API_V1}/generation/status`, () => {
    return HttpResponse.json<GenerationStatus>({
      enabled: true,
      models: null,
      default_model: null,
    });
  }),
  http.get(`${API_V1}/practice/status`, () => {
    return HttpResponse.json<PracticeStatus>({
      enabled: true,
      models: null,
      default_model: null,
    });
  }),
  http.post(`${API_V1}/practice/turn`, () => {
    return HttpResponse.json<PracticeTurnResponse>({
      turn: practiceOpeningTurn,
      history: practiceHistory,
    });
  }),
  http.post(`${API_V1}/generation/draft`, () => {
    return HttpResponse.json<GenerationDraftResponse>({
      draft: packDraft,
      history: generationHistory,
    });
  }),
  http.post(`${API_V1}/generation/packs`, async ({ request }) => {
    const body = (await request.json()) as { draft: PackDraft };
    return HttpResponse.json<PackDetail>(savedPackFromDraft(body.draft), { status: 201 });
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
  http.delete(`${API_V1}/packs/:packId`, ({ params }) => {
    const packId = String(params.packId);
    const pack = packDetails[packId];
    if (!pack) {
      return HttpResponse.json(
        { error: { code: "not_found", message: "pack not found", request_id: "mock-request" } },
        { status: 404 },
      );
    }
    // The real server rejects deleting a curated (unowned) pack with 403.
    if (!pack.owned) {
      return HttpResponse.json(
        {
          error: {
            code: "http_403",
            message: "cannot delete a curated pack",
            request_id: "mock-request",
          },
        },
        { status: 403 },
      );
    }
    return new HttpResponse(null, { status: 204 });
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
