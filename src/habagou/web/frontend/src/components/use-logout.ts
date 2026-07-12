import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { getAuthSession, logout } from "../lib/api";

// Shared session + logout wiring for the app shell headers. Returns the session
// query, the display-name fallback chain, and a logout handler that clears the
// cached session and redirects to /login.
export function useLogout() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const session = useQuery({ queryKey: ["auth", "session"], queryFn: getAuthSession });
  const displayName = session.data?.user?.display_name ?? session.data?.user?.username ?? "Learner";

  async function handleLogout() {
    await logout();
    queryClient.setQueryData(["auth", "session"], {
      authenticated: false,
      provider: session.data?.provider ?? "keycloak",
      user: null,
    });
    await navigate({ to: "/login" });
  }

  return { session, displayName, handleLogout };
}
