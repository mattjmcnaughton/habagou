// Learning Path API types, derived from the generated OpenAPI schema.
//
// The generated `PathContentDTO` is intentionally opaque (`{ [key: string]:
// unknown }`) because the backend serializes item content with a single-key
// `model_serializer`, so openapi-typescript cannot describe the trace/match/
// sentence union. `PathContent` below fills that one gap by hand; every other
// shape is a derivation of `components["schemas"]` so a future `just
// openapi-export` that drifts these fields fails `just typecheck` here.

import type { components } from "./api-types";

type Gen = components["schemas"];

export type PathActivity = Gen["PathItemDTO"]["activity"];
export type PathItemKind = Gen["PathItemDTO"]["kind"];
export type PathItemState = Gen["PathItemDTO"]["state"];

export type PathCharacter = Gen["PathCharDTO"];
export type PathSentence = Gen["PathSentenceContentDTO"];
export type PathPack = Gen["PathPackDTO"];

export type PathContent = {
  trace?: Gen["PathTraceContentDTO"];
  match?: Gen["PathMatchContentDTO"];
  sentence?: Gen["PathSentenceContentDTO"];
};

export type PathItem = Omit<Gen["PathItemDTO"], "content"> & { content: PathContent };

export type DailyGoal = Gen["PathDailyDTO"];

export type PathDue = Gen["PathDueDTO"];

export type PathResponse = Omit<Gen["PathResponseDTO"], "items"> & { items: PathItem[] };

export type CompletePathItemBody = Gen["PathItemCompleteDTO"];

export type CompletePathItemResponse = Gen["PathItemCompleteResponseDTO"];
