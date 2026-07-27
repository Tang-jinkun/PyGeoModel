import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { createServer, request } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { createStaticServer } from "./server.mjs";

const cleanups: Array<() => Promise<void>> = [];

afterEach(async () => {
  await Promise.all(cleanups.splice(0).map((cleanup) => cleanup()));
});

describe("static server", () => {
  it("proxies API requests to the configured backend", async () => {
    const root = await mkdtemp(join(tmpdir(), "pygeomodel-static-"));
    await writeFile(join(root, "index.html"), "frontend", "utf8");
    const backend = createServer((incoming, response) => {
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify({ path: incoming.url }));
    });
    await new Promise<void>((resolve) => backend.listen(0, "127.0.0.1", resolve));
    const backendAddress = backend.address();
    if (!backendAddress || typeof backendAddress === "string") throw new Error("Expected backend address");
    const server = createStaticServer(root, `http://127.0.0.1:${backendAddress.port}`);
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    cleanups.push(async () => {
      await Promise.all([
        new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve())),
        new Promise<void>((resolve, reject) => backend.close((error) => error ? reject(error) : resolve()))
      ]);
      await rm(root, { recursive: true, force: true });
    });
    const address = server.address();
    if (!address || typeof address === "string") throw new Error("Expected frontend address");

    const response = await getResponse(address.port, "/api/health?source=workspace");

    expect(response).toEqual({ status: 200, body: '{"path":"/api/health?source=workspace"}' });
  });

  it("returns 400 for a malformed percent-encoded path", async () => {
    const root = await mkdtemp(join(tmpdir(), "pygeomodel-static-"));
    await writeFile(join(root, "index.html"), "ok", "utf8");
    const server = createStaticServer(root);
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    cleanups.push(async () => {
      await new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
      await rm(root, { recursive: true, force: true });
    });
    const address = server.address();
    if (!address || typeof address === "string") throw new Error("Expected TCP server address");

    const response = await getResponse(address.port, "/%ZZ");

    expect(response).toEqual({ status: 400, body: "Bad Request" });
  });
});

function getResponse(port: number, path: string) {
  return new Promise<{ status: number | undefined; body: string }>((resolve, reject) => {
    const outgoing = request({ host: "127.0.0.1", port, path }, (incoming) => {
      let body = "";
      incoming.setEncoding("utf8");
      incoming.on("data", (chunk) => { body += chunk; });
      incoming.on("end", () => resolve({ status: incoming.statusCode, body }));
    });
    outgoing.on("error", reject);
    outgoing.end();
  });
}
