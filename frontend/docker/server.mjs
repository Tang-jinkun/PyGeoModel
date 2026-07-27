import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";

const root = resolve(process.env.PYGEOMODEL_FRONTEND_DIST ?? "/app/dist");
const port = Number(process.env.PORT ?? 5173);
const types = new Map([
  [".css", "text/css; charset=utf-8"], [".html", "text/html; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"], [".json", "application/json; charset=utf-8"],
  [".png", "image/png"], [".svg", "image/svg+xml"], [".woff2", "font/woff2"]
]);

createServer(async (request, response) => {
  const pathname = decodeURIComponent(new URL(request.url ?? "/", "http://localhost").pathname);
  let candidate = resolve(root, `.${pathname}`);
  if (candidate !== root && !candidate.startsWith(`${root}${sep}`)) {
    response.writeHead(400).end("Bad Request");
    return;
  }
  if (!(await isFile(candidate))) candidate = resolve(root, "index.html");
  response.setHeader("Content-Type", types.get(extname(candidate)) ?? "application/octet-stream");
  response.setHeader(
    "Cache-Control",
    candidate.endsWith(`${sep}runtime-config.js`) ? "no-store" : "public, max-age=3600"
  );
  createReadStream(candidate).pipe(response);
}).listen(port, "0.0.0.0");

async function isFile(path) {
  try { return (await stat(path)).isFile(); } catch { return false; }
}
