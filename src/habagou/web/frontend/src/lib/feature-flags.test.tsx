import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { authenticatedSession } from "../mocks/handlers";
import { server } from "../mocks/server";
import { API_V1_BASE } from "./api";
import { useFeatureFlag } from "./feature-flags";

// No flags are registered in code today, so exercise the generic hook with a
// placeholder key.
const EXAMPLE_FLAG = "example_flag";

function Probe() {
  const enabled = useFeatureFlag(EXAMPLE_FLAG);
  return <span>{enabled ? "flag-on" : "flag-off"}</span>;
}

function renderProbe() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <Probe />
    </QueryClientProvider>,
  );
}

describe("useFeatureFlag", () => {
  it("resolves to off when the session does not enable the flag", async () => {
    renderProbe();
    expect(await screen.findByText("flag-off")).toBeTruthy();
  });

  it("resolves to on when the session enables the flag (e.g. an admin)", async () => {
    server.use(
      http.get(`${API_V1_BASE}/auth/session`, () =>
        HttpResponse.json({
          ...authenticatedSession,
          user: {
            ...authenticatedSession.user,
            feature_flags: { [EXAMPLE_FLAG]: true },
          },
        }),
      ),
    );
    renderProbe();
    expect(await screen.findByText("flag-on")).toBeTruthy();
  });
});
