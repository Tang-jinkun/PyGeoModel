import { mkdir, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

const output = process.argv[2] ?? "/app/dist/runtime-config.js";
const config = {
  apiBaseUrl: process.env.PYGEOMODEL_API_BASE_URL ?? ""
};
await mkdir(dirname(output), { recursive: true });
await writeFile(
  output,
  `window.__PYGEOMODEL_RUNTIME_CONFIG__ = ${JSON.stringify(config)};\n`,
  "utf8"
);
