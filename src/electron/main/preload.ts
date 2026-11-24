/**
 * Context-isolated Electron Preload Bridge for W5CDN RadioPlanner.
 * Exposes window.desktopApi (and temporary window.pywebview alias during PR 1 transition).
 */

import { contextBridge, ipcRenderer } from "electron";

interface SaveFileResult {
  saved: boolean;
  path?: string;
  cancelled?: boolean;
  error?: string;
}

const desktopApi = {
  isElectron: true,
  platform: process.platform,
  saveTextFile: (filename: string, content: string): Promise<SaveFileResult> =>
    ipcRenderer.invoke("desktop:saveTextFile", filename, content),
  openDataFolder: (): Promise<{ ok: boolean; path?: string }> =>
    ipcRenderer.invoke("desktop:openDataFolder"),
  getAppInfo: (): Promise<{ version: string; configDir: string; platform: string }> =>
    ipcRenderer.invoke("desktop:getAppInfo"),
};

contextBridge.exposeInMainWorld("desktopApi", desktopApi);

// Backwards-compatible bridge while PR 1 keeps src/web/static/app.js compatible with Python pywebview
contextBridge.exposeInMainWorld("pywebview", {
  api: {
    save_text_file: (filename: string, content: string): Promise<SaveFileResult> =>
      ipcRenderer.invoke("desktop:saveTextFile", filename, content),
  },
});
