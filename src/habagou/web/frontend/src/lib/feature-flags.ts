import { useQuery } from "@tanstack/react-query";
import { getAuthSession } from "./api";

// Feature flags are delivered as part of the auth session (`user.feature_flags`,
// resolved per user on the backend). Reading them is just reading that same
// cached session query — no extra request — so any component can gate on a flag
// without new plumbing. Unknown/absent flags resolve to off.

export const AUDIO_PRONUNCIATION_FLAG = "audio_pronunciation";

export function useFeatureFlag(key: string): boolean {
  const session = useQuery({ queryKey: ["auth", "session"], queryFn: getAuthSession });
  return session.data?.user?.feature_flags?.[key] ?? false;
}
