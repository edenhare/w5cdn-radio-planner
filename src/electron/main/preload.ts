/**
 * Context-isolated Electron Preload Bridge for W5CDN RadioPlanner.
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
  openDataFolder: (): Promise<{ ok: boolean; path?: string; error?: string }> =>
    ipcRenderer.invoke("desktop:openDataFolder"),
  getAppInfo: (): Promise<{ version: string; configDir: string; platform: string }> =>
    ipcRenderer.invoke("desktop:getAppInfo"),
};

contextBridge.exposeInMainWorld("desktopApi", desktopApi);
