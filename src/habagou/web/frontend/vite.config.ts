import react from "@vitejs/plugin-react";
import { TanStackRouterVite } from "@tanstack/router-plugin/vite";
import { defineConfig } from "vitest/config";

const backendPort = process.env.HABAGOU_PORT ?? "8000";
const frontendPort = Number.parseInt(process.env.VITE_PORT ?? "5173", 10);
const apiProxyTarget = process.env.VITE_API_PROXY_TARGET ?? `http://127.0.0.1:${backendPort}`;

export default defineConfig({
  plugins: [TanStackRouterVite(), react()],
  resolve: {
    alias: {
      "@": "/src",
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./tests/setup.ts",
    include: ["src/**/*.test.{ts,tsx}"],
  },
  server: {
    host: "127.0.0.1",
    port: frontendPort,
    strictPort: true,
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
      "/auth": {
        target: apiProxyTarget,
        changeOrigin: false,
      },
    },
  },
});
