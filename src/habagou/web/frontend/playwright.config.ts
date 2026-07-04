import { defineConfig, devices } from "@playwright/test";

const frontendPort = Number.parseInt(
  process.env.PLAYWRIGHT_PORT ?? process.env.VITE_PORT ?? "15341",
  10,
);
const backendPort = Number.parseInt(process.env.HABAGOU_PORT ?? "8000", 10);
const frontendURL = `http://127.0.0.1:${frontendPort}`;
const backendURL = `http://127.0.0.1:${backendPort}`;
const baseURL = process.env.BASE_URL ?? frontendURL;
const localBrowserChannel = process.env.CI ? undefined : "chrome";

export default defineConfig({
  fullyParallel: false,
  reporter: [
    ["list"],
    ["json", { outputFile: "../../../../.artifacts/test-results/playwright.json" }],
  ],
  testDir: "./tests/e2e",
  use: {
    baseURL,
    trace: "retain-on-failure",
  },
  webServer: process.env.BASE_URL
    ? undefined
    : [
        {
          command: `bash -lc 'cd ../../../.. && just bootstrap && uv run uvicorn habagou.app:app --host 127.0.0.1 --port ${backendPort}'`,
          reuseExistingServer: true,
          timeout: 120_000,
          url: `${backendURL}/readyz`,
        },
        {
          command: `bash -lc 'HABAGOU_PORT=${backendPort} VITE_API_PROXY_TARGET=${backendURL} pnpm run dev --host 127.0.0.1 --port ${frontendPort}'`,
          reuseExistingServer: true,
          timeout: 120_000,
          url: frontendURL,
        },
      ],
  workers: 1,
  projects: [
    {
      name: "desktop",
      use: {
        ...devices["Desktop Chrome"],
        ...(localBrowserChannel ? { channel: localBrowserChannel } : {}),
      },
    },
    {
      name: "mobile-390x844",
      use: {
        ...devices["Pixel 5"],
        ...(localBrowserChannel ? { channel: localBrowserChannel } : {}),
        viewport: { height: 844, width: 390 },
      },
    },
  ],
});
