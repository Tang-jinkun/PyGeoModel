import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { request } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { createStaticServer } from "./server.mjs";

const cleanups: Array<() => Promise<void>> = [];

afterEach(async () => {
  await Promise.all(cleanups.splice(0).map((cleanup) => cleanup()));
});

describe("static server", () => {
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

    const response = await new Promise<{ status: number | undefined; body: string }>((resolve, reject) => {
      const outgoing = request({ host: "127.0.0.1", port: address.port, path: "/%ZZ" }, (incoming) => {
        let body = "";
        incoming.setEncoding("utf8");
        incoming.on("data", (chunk) => { body += chunk; });
        incoming.on("end", () => resolve({ status: incoming.statusCode, body }));
      });
      outgoing.on("error", reject);
      outgoing.end();
    });

    expect(response).toEqual({ status: 400, body: "Bad Request" });
  });
});
