import type { QueryClient } from "@tanstack/react-query";
import type { PackDetail } from "./api";
import { getCharacterStrokes } from "./api";

export const STROKE_QUERY_STALE_TIME = Number.POSITIVE_INFINITY;

export function characterStrokesQueryKey(hanzi: string) {
  return ["character-strokes", hanzi] as const;
}

export function characterStrokesQueryOptions(hanzi: string) {
  return {
    queryKey: characterStrokesQueryKey(hanzi),
    queryFn: () => getCharacterStrokes(hanzi),
    staleTime: STROKE_QUERY_STALE_TIME,
  };
}

export function collectPackStrokeCharacters(pack: Pick<PackDetail, "characters" | "sentences">) {
  const hanzi = new Set<string>();
  for (const character of pack.characters) {
    hanzi.add(character.hanzi);
  }
  for (const sentence of pack.sentences) {
    for (const character of Array.from(sentence.hanzi)) {
      hanzi.add(character);
    }
  }
  return [...hanzi];
}

export function prefetchPackStrokeData(
  queryClient: QueryClient,
  pack: Pick<PackDetail, "characters" | "sentences">,
) {
  return Promise.all(
    collectPackStrokeCharacters(pack).map((hanzi) =>
      queryClient.prefetchQuery(characterStrokesQueryOptions(hanzi)),
    ),
  );
}
