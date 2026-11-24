/**
 * Ephemeral Localhost HTTP Server Adapter for Playwright E2E & Integration Tests.
 * Serves the exact same ApiRouter and static UI directory used by the Electron app:// protocol.
 */

import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { resolveStaticDir } from "./paths";
import { ApiRouter } from "./router";
import { WebWorkspace } from "./workspace";

const MIME_TYPES: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".png": "image/png",
  ".woff2": "font/woff2",
  ".yaml": "application/x-yaml; charset=utf-8",
};

export interface TestServerHandle {
  server: http.Server;
  url: string;
  port: number;
  router: ApiRouter;
  close(): Promise<void>;
}

export async function startTestServer(opts?: {
  baseDir?: string;
  port?: number;
  offlineOnly?: boolean;
  staticDir?: string;
}): Promise<TestServerHandle> {
  const workspace = new WebWorkspace({
    baseDir: opts?.baseDir,
    loadPersistedSession: false,
    offlineOnly: opts?.offlineOnly ?? true,
  });
  const router = new ApiRouter(workspace);
  const staticDir = path.resolve(opts?.staticDir ?? resolveStaticDir());

  const server = http.createServer(async (req, res) => {
    const reqUrl = new URL(req.url || "/", "http://127.0.0.1");
    const pathname = reqUrl.pathname;

    if (pathname.startsWith("/api/")) {
      const chunks: Buffer[] = [];
      for await (const chunk of req) {
        chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
      }
      const bodyBuffer = Buffer.concat(chunks);
      const result = await router.handle({
        method: req.method || "GET",
        pathname,
        query: reqUrl.searchParams,
        bodyBuffer,
        bodyText: bodyBuffer.toString("utf-8"),
      });
      res.writeHead(result.status, result.headers);
      res.end(result.body);
      return;
    }

    let relPath = pathname === "/" ? "index.html" : pathname.replace(/^\/+/, "");
    if (relPath.startsWith("static/")) {
      relPath = relPath.slice("static/".length);
    }
    if (relPath === "favicon.ico") {
      relPath = fs.existsSync(path.join(staticDir, "icon.ico")) ? "icon.ico" : "icon.svg";
    }

    const resolved = path.resolve(staticDir, relPath);
    if (!resolved.startsWith(staticDir + path.sep) && resolved !== staticDir) {
      res.writeHead(403);
      res.end("Forbidden");
      return;
    }

    if (!fs.existsSync(resolved) || !fs.statSync(resolved).isFile()) {
      res.writeHead(404);
      res.end("Not Found");
      return;
    }

    const ext = path.extname(resolved).toLowerCase();
    res.writeHead(200, { "Content-Type": MIME_TYPES[ext] || "application/octet-stream" });
    res.end(fs.readFileSync(resolved));
  });

  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(opts?.port ?? 0, "127.0.0.1", () => resolve());
  });

  const addr = server.address();
  const port = typeof addr === "object" && addr ? addr.port : 0;

  return {
    server,
    port,
    url: `http://127.0.0.1:${port}`,
    router,
    close: () =>
      new Promise<void>((resolve, reject) => {
        server.close((err) => (err ? reject(err) : resolve()));
      }),
  };
}
