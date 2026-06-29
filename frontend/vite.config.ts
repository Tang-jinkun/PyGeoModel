import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

const proxyTarget = process.env.VITE_PROXY_TARGET ?? "http://localhost:8000";
const basePath = normalizeBasePath(process.env.VITE_BASE_PATH ?? "/");
const basePrefix = basePath === "/" ? "" : basePath.slice(0, -1);

function normalizeBasePath(value: string) {
  const withLeadingSlash = value.startsWith("/") ? value : `/${value}`;
  return withLeadingSlash.endsWith("/") ? withLeadingSlash : `${withLeadingSlash}/`;
}

const proxy: NonNullable<ReturnType<typeof defineConfig>["server"]>["proxy"] = {
  "/api": proxyTarget,
  "/outputs": proxyTarget
};

if (basePrefix) {
  proxy[`${basePrefix}/api`] = {
    target: proxyTarget,
    changeOrigin: true,
    rewrite: (path) => path.replace(`${basePrefix}/api`, "/api")
  };
  proxy[`${basePrefix}/outputs`] = {
    target: proxyTarget,
    changeOrigin: true,
    rewrite: (path) => path.replace(`${basePrefix}/outputs`, "/outputs")
  };
}

export default defineConfig({
  base: basePath,
  plugins: [vue()],
  server: {
    port: 5173,
    proxy
  }
});
