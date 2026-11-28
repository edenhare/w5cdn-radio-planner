/**
 * Electron Main Process Entrypoint for W5CDN RadioPlanner.
 *
 * - Serves the SPA offline via privileged custom protocol `app://local/`
 * - Routes all `/api/*` requests directly in-process via ApiRouter (zero localhost server)
 * - Unifies userData under `%APPDATA%\W5CDN\RadioPlanner` (or legacy `~/.config/radioplanner`)
 * - Provides native OS Save dialogs, Open Config Folder, right-click spellcheck/clipboard menu
 * - Supports live end-to-end smoke verification via `RADIOPLANNER_SMOKE_TEST=1`
 */

import fs from "node:fs";
import path from "node:path";
import { app, BrowserWindow, dialog, ipcMain, Menu, protocol, shell } from "electron";
import { sanitizeFilename, sanitizeHttpUrl } from "../shared/sanitize";
import { getConfigDir, resolveStaticDir } from "./paths";
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

// Must be called before app.whenReady()
protocol.registerSchemesAsPrivileged([
  {
    scheme: "app",
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      corsEnabled: true,
    },
  },
]);

// Align Electron's own userData folder with the unified W5CDN\RadioPlanner config directory
const resolvedConfigDir = getConfigDir();
if (app.isPackaged || process.env.RADIOPLANNER_HOME || process.env.W5CDN_SUITE_DIR) {
  app.setPath("userData", resolvedConfigDir);
}

let mainWindow: BrowserWindow | null = null;
let workspace: WebWorkspace | null = null;
let router: ApiRouter | null = null;

function registerProtocolHandler(apiRouter: ApiRouter, staticDir: string): void {
  const resolvedStatic = path.resolve(staticDir);

  protocol.handle("app", async (request) => {
    const reqUrl = new URL(request.url);
    const pathname = reqUrl.pathname;

    if (pathname.startsWith("/api/")) {
      let bodyBuffer: Buffer | undefined;
      let bodyText: string | undefined;
      if (request.method !== "GET" && request.method !== "HEAD") {
        const arrBuf = await request.arrayBuffer();
        bodyBuffer = Buffer.from(arrBuf);
        bodyText = bodyBuffer.toString("utf-8");
      }
      const res = await apiRouter.handle({
        method: request.method,
        pathname,
        query: reqUrl.searchParams,
        bodyBuffer,
        bodyText,
      });
      const responseBody = Buffer.isBuffer(res.body) ? new Uint8Array(res.body) : res.body;
      return new Response(responseBody, {
        status: res.status,
        headers: res.headers,
      });
    }

    let relPath = pathname === "/" ? "index.html" : pathname.replace(/^\/+/, "");
    if (relPath.startsWith("static/")) {
      relPath = relPath.slice("static/".length);
    }
    if (relPath === "favicon.ico") {
      relPath = fs.existsSync(path.join(resolvedStatic, "icon.ico")) ? "icon.ico" : "icon.svg";
    }

    const target = path.resolve(resolvedStatic, relPath);
    if (!target.startsWith(resolvedStatic + path.sep) && target !== resolvedStatic) {
      return new Response("Forbidden", { status: 403 });
    }

    if (!fs.existsSync(target) || !fs.statSync(target).isFile()) {
      return new Response("Not Found", { status: 404 });
    }

    const ext = path.extname(target).toLowerCase();
    const content = fs.readFileSync(target);
    return new Response(new Uint8Array(content), {
      status: 200,
      headers: {
        "Content-Type": MIME_TYPES[ext] || "application/octet-stream",
        "X-Content-Type-Options": "nosniff",
      },
    });
  });
}

function registerIpcHandlers(apiRouter: ApiRouter): void {
  ipcMain.handle("desktop:saveTextFile", async (_event, filename: string, content: string) => {
    const safeName = sanitizeFilename(filename || "export.txt", "export.txt");
    const ext = path.extname(safeName).toLowerCase();
    const filters =
      ext === ".csv"
        ? [{ name: "CSV Codeplug", extensions: ["csv"] }, { name: "All Files", extensions: ["*"] }]
        : ext === ".yaml" || ext === ".yml"
          ? [{ name: "YAML Configuration", extensions: ["yaml", "yml"] }, { name: "All Files", extensions: ["*"] }]
          : ext === ".json"
            ? [{ name: "JSON File", extensions: ["json"] }, { name: "All Files", extensions: ["*"] }]
            : [{ name: "Text File", extensions: ["txt"] }, { name: "All Files", extensions: ["*"] }];

    const result = await dialog.showSaveDialog(mainWindow ?? undefined!, {
      defaultPath: safeName,
      filters,
    });
    if (result.canceled || !result.filePath) {
      return { saved: false, cancelled: true };
    }
    try {
      fs.writeFileSync(result.filePath, String(content ?? ""), "utf-8");
      return { saved: true, path: result.filePath };
    } catch (err) {
      return { saved: false, error: err instanceof Error ? err.message : "Write failed" };
    }
  });

  ipcMain.handle("desktop:openDataFolder", async () => {
    const dir = apiRouter.workspace.baseDir;
    fs.mkdirSync(dir, { recursive: true });
    const errMsg = await shell.openPath(dir);
    return { ok: !errMsg, path: dir, error: errMsg || undefined };
  });

  ipcMain.handle("desktop:getAppInfo", () => ({
    version: apiRouter.appVersion,
    configDir: apiRouter.workspace.baseDir,
    platform: process.platform,
  }));
}

function attachContextMenu(win: BrowserWindow): void {
  win.webContents.on("context-menu", (_event, params) => {
    const template: Electron.MenuItemConstructorOptions[] = [];

    if (params.misspelledWord && params.dictionarySuggestions.length > 0) {
      for (const suggestion of params.dictionarySuggestions.slice(0, 6)) {
        template.push({
          label: suggestion,
          click: () => win.webContents.replaceMisspelling(suggestion),
        });
      }
      template.push({ type: "separator" });
    }

    if (params.isEditable) {
      template.push(
        { role: "undo" },
        { role: "redo" },
        { type: "separator" },
        { role: "cut" },
        { role: "copy" },
        { role: "paste" },
        { role: "selectAll" },
      );
    } else if (params.selectionText) {
      template.push({ role: "copy" }, { role: "selectAll" });
    }

    if (template.length > 0) {
      Menu.buildFromTemplate(template).popup({ window: win });
    }
  });
}

function createMainWindow(isSmokeTest: boolean): BrowserWindow {
  const staticDir = resolveStaticDir();
  const iconCandidate = path.join(staticDir, process.platform === "win32" ? "icon.ico" : "icon.png");

  const win = new BrowserWindow({
    width: 1460,
    height: 940,
    minWidth: 1024,
    minHeight: 700,
    title: "W5CDN RadioPlanner",
    show: !isSmokeTest,
    icon: fs.existsSync(iconCandidate) ? iconCandidate : undefined,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: true,
    },
  });

  win.setMenuBarVisibility(false);
  attachContextMenu(win);

  win.webContents.setWindowOpenHandler(({ url }) => {
    const safe = sanitizeHttpUrl(url);
    if (safe) {
      void shell.openExternal(safe);
    }
    return { action: "deny" };
  });

  win.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith("app://local/")) {
      event.preventDefault();
      const safe = sanitizeHttpUrl(url);
      if (safe) {
        void shell.openExternal(safe);
      }
    }
  });

  void win.loadURL("app://local/");
  return win;
}

async function runSmokeCheck(win: BrowserWindow): Promise<void> {
  const consoleErrors: string[] = [];
  win.webContents.on("console-message", (event) => {
    const details = event as unknown as { level?: number; message?: string };
    if (typeof details.level === "number" && details.level >= 3) {
      consoleErrors.push(String(details.message || "Console error"));
    }
  });

  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Timed out waiting for did-finish-load")), 15000);
    win.webContents.once("did-finish-load", () => {
      clearTimeout(timer);
      resolve();
    });
  });

  // Give bootstrap JS a moment to populate config and render
  await new Promise((r) => setTimeout(r, 800));

  const smokeResult = (await win.webContents.executeJavaScript(`
    (async () => {
      const cfgRes = await fetch('/api/config');
      const cfg = await cfgRes.json();
      if (!cfgRes.ok || !Array.isArray(cfg.radios) || cfg.radios.length === 0) {
        return { ok: false, step: 'config', detail: cfg };
      }

      const planRes = await fetch('/api/plan/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: 'ROUTE_CORRIDOR',
          waypoints: ['Tyler, TX', 'Shreveport, LA'],
          corridor_width: 25,
          radio_id: 'baofeng_5rm'
        })
      });
      const plan = await planRes.json();
      if (!planRes.ok || !plan.active || !plan.codeplug || plan.codeplug.total_channels === 0) {
        return { ok: false, step: 'generate', detail: plan };
      }

      const expRes = await fetch('/api/codeplug/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ programmer_type: 'CHIRP', filename: 'smoke.csv' })
      });
      const csvText = await expRes.text();
      if (!expRes.ok || !csvText.includes('Location,Name,Frequency')) {
        return { ok: false, step: 'export_csv', detail: csvText.slice(0, 120) };
      }

      const yamlRes = await fetch('/api/radios/baofeng_5rm/export');
      const yamlText = await yamlRes.text();
      if (!yamlRes.ok || !yamlText.includes('id: baofeng_5rm')) {
        return { ok: false, step: 'export_radio_yaml', detail: yamlText.slice(0, 120) };
      }

      const title = document.title;
      return {
        ok: true,
        title,
        radios: cfg.radios.length,
        templates: cfg.templates.length,
        channels: plan.codeplug.total_channels
      };
    })()
  `)) as { ok: boolean; step?: string; detail?: unknown; radios?: number; templates?: number; channels?: number };

  if (!smokeResult.ok || consoleErrors.length > 0) {
    console.error("ELECTRON_RADIOPLANNER_SMOKE_FAILED", JSON.stringify({ smokeResult, consoleErrors }));
    app.exit(1);
    return;
  }

  console.log(
    `ELECTRON_RADIOPLANNER_SMOKE_OK radios=${smokeResult.radios} templates=${smokeResult.templates} channels=${smokeResult.channels}`,
  );
  app.exit(0);
}

app.whenReady().then(async () => {
  const isSmokeTest = process.env.RADIOPLANNER_SMOKE_TEST === "1";
  workspace = new WebWorkspace({
    baseDir: resolvedConfigDir,
    loadPersistedSession: !isSmokeTest,
    offlineOnly: isSmokeTest,
  });
  router = new ApiRouter(workspace);
  router.onUpdateRestartRequested = () => {
    app.quit();
  };
  const staticDir = resolveStaticDir();

  registerProtocolHandler(router, staticDir);
  registerIpcHandlers(router);

  mainWindow = createMainWindow(isSmokeTest);
  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  if (isSmokeTest) {
    try {
      await runSmokeCheck(mainWindow);
    } catch (err) {
      console.error("ELECTRON_RADIOPLANNER_SMOKE_FAILED", err instanceof Error ? err.message : String(err));
      app.exit(1);
    }
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0 && router) {
    mainWindow = createMainWindow(false);
  }
});
