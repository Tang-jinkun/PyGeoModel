import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vitest/config";

const proxyTarget = process.env.VITE_PROXY_TARGET ?? "http://localhost:8000";
const proxy: NonNullable<ReturnType<typeof defineConfig>["server"]>["proxy"] = {
  "/api": proxyTarget
};

export default defineConfig({
  base: "./",
  plugins: [vue()],
  server: {
    port: 5173,
    proxy
  },
  test: {
    environment: "happy-dom",
    setupFiles: ["./src/test/setup.ts"],
    restoreMocks: true
  }
});
