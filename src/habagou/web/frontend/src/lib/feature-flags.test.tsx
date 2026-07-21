import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { authenticatedSession } from "../mocks/handlers";
import { server } from "../mocks/server";
import { API_V1_BASE } from "./api";
import { AUDIO_PRONUNCIATION_FLAG, useFeatureFlag } from "./feature-flags";

function Probe() {
  const enabled = useFeatureFlag(AUDIO_PRONUNCIATION_FLAG);
  return <span>{enabled ? "audio-on" : "audio-off"}</span>;
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
    expect(await screen.findByText("audio-off")).toBeTruthy();
  });

  it("resolves to on when the session enables the flag (e.g. an admin)", async () => {
    server.use(
      http.get(`${API_V1_BASE}/auth/session`, () =>
        HttpResponse.json({
          ...authenticatedSession,
          user: {
            ...authenticatedSession.user,
            feature_flags: { [AUDIO_PRONUNCIATION_FLAG]: true },
          },
        }),
      ),
    );
    renderProbe();
    expect(await screen.findByText("audio-on")).toBeTruthy();
  });
});
