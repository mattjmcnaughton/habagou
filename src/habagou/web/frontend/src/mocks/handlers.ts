import { HttpResponse, http } from "msw";
import type { PackSummary } from "../lib/api";

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
];

export const handlers = [
  http.get(`${API_V1}/packs`, () => {
    return HttpResponse.json<PackSummary[]>(packSummaries);
  }),
];
