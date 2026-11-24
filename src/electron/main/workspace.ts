/**
 * Active Workspace State Manager for W5CDN RadioPlanner.
 * Holds active plan session, bounded 20-step undo stack, session.json persistence, and all managers/providers.
 */

import fs from "node:fs";
import path from "node:path";
import {
  RadioChannel,
  RadioPlannerRecipe,
  TargetRadioSpec,
  createRadioChannel,
} from "../shared/types";
import { validateRadioSpec, validateRecipe } from "../shared/yamlDiagnostics";
import { PreferencesManager, RadioManager, RecipeManager, TemplateManager } from "./managers";
import { ensureConfigDirectories, getCacheDir, getConfigDir, getSessionFile } from "./paths";
import { AirportsProvider } from "./providers/airports";
import { CallsignLookupService } from "./providers/callsignLookup";
import { GeocodingProvider } from "./providers/geocoding";
import { NwsAlertsService } from "./providers/nws";
import { RadioIdProvider } from "./providers/radioId";
import { RepeaterBookProvider } from "./providers/repeaterbook";

export const MAX_UNDO_HISTORY = 20;

export interface CodeplugState {
  name: string;
  channels: RadioChannel[];
}

export interface UndoSnapshot {
  channels: RadioChannel[];
  raw_channels: RadioChannel[];
  primary_channels: RadioChannel[];
  deleted_keys: Set<string>;
  label: string;
}

export function channelDeleteKey(ch: Pick<RadioChannel, "rxFreq" | "callsign" | "city">): string {
  return `${ch.rxFreq.toFixed(4)}|${ch.callsign ?? ""}|${ch.city ?? ""}`;
}

export class ActivePlanSessionState {
  recipe: RadioPlannerRecipe | null = null;
  codeplug: CodeplugState | null = null;
  radio_spec: TargetRadioSpec | null = null;
  primary_channels: RadioChannel[] = [];
  raw_channels: RadioChannel[] = [];
  deleted_keys: Set<string> = new Set();
  map_data: Record<string, unknown> = {};
  summary_data: Record<string, unknown> = {};
  notices: Array<{ level: string; message: string }> = [];
  undo_stack: UndoSnapshot[] = [];

  pushUndo(label = "Channel change"): void {
    if (!this.codeplug) return;
    this.undo_stack.push({
      channels: this.codeplug.channels.map((c) => ({ ...c })),
      raw_channels: this.raw_channels.map((c) => ({ ...c })),
      primary_channels: this.primary_channels.map((c) => ({ ...c })),
      deleted_keys: new Set(this.deleted_keys),
      label,
    });
    if (this.undo_stack.length > MAX_UNDO_HISTORY) {
      this.undo_stack = this.undo_stack.slice(-MAX_UNDO_HISTORY);
    }
  }

  popUndo(): UndoSnapshot | null {
    return this.undo_stack.pop() ?? null;
  }

  toPersistedDict(): Record<string, unknown> {
    if (!this.recipe || !this.codeplug || !this.radio_spec) {
      return { active: false };
    }
    return {
      active: true,
      recipe: this.recipe,
      codeplug: {
        name: this.codeplug.name,
        channels: this.codeplug.channels,
      },
      radio_spec: this.radio_spec,
      primary_channels: this.primary_channels,
      raw_channels: this.raw_channels,
      deleted_keys: Array.from(this.deleted_keys).sort(),
      map_data: this.map_data,
      summary_data: this.summary_data,
      notices: this.notices,
    };
  }

  static fromPersistedDict(data: unknown): ActivePlanSessionState {
    const sess = new ActivePlanSessionState();
    if (!data || typeof data !== "object" || !(data as Record<string, unknown>).active) {
      return sess;
    }
    const obj = data as Record<string, unknown>;
    try {
      const recipe = validateRecipe(obj.recipe as Record<string, unknown>, "session.json");
      const radioSpec = validateRadioSpec(obj.radio_spec as Record<string, unknown>, "session.json");
      const cpRaw = obj.codeplug as { name?: string; channels?: Array<Partial<RadioChannel> & { name: string; rxFreq: number }> };
      if (!cpRaw || !Array.isArray(cpRaw.channels)) return sess;

      sess.recipe = recipe;
      sess.radio_spec = radioSpec;
      sess.codeplug = {
        name: String(cpRaw.name || recipe.name),
        channels: cpRaw.channels.map((c) => createRadioChannel(c)),
      };
      sess.primary_channels = Array.isArray(obj.primary_channels)
        ? obj.primary_channels.map((c) => createRadioChannel(c as Partial<RadioChannel> & { name: string; rxFreq: number }))
        : [];
      sess.raw_channels = Array.isArray(obj.raw_channels)
        ? obj.raw_channels.map((c) => createRadioChannel(c as Partial<RadioChannel> & { name: string; rxFreq: number }))
        : [];
      if (Array.isArray(obj.deleted_keys)) {
        for (const item of obj.deleted_keys) {
          if (typeof item === "string") {
            sess.deleted_keys.add(item);
          } else if (Array.isArray(item) && item.length === 3) {
            sess.deleted_keys.add(`${Number(item[0]).toFixed(4)}|${String(item[1])}|${String(item[2])}`);
          }
        }
      }
      sess.map_data = (obj.map_data as Record<string, unknown>) ?? {};
      sess.summary_data = (obj.summary_data as Record<string, unknown>) ?? {};
      sess.notices = Array.isArray(obj.notices)
        ? (obj.notices as Array<{ level: string; message: string }>)
        : [];
    } catch {
      return new ActivePlanSessionState();
    }
    return sess;
  }
}

export interface WorkspaceOptions {
  baseDir?: string;
  loadPersistedSession?: boolean;
  offlineOnly?: boolean;
}

export class WebWorkspace {
  readonly baseDir: string;
  readonly offlineOnly: boolean;
  radioMgr: RadioManager;
  prefsMgr: PreferencesManager;
  templateMgr: TemplateManager;
  recipeMgr: RecipeManager;
  geocoder: GeocodingProvider;
  repeaterProvider: RepeaterBookProvider;
  airportsProvider: AirportsProvider;
  radioIdProvider: RadioIdProvider;
  lookupService: CallsignLookupService;
  nwsService: NwsAlertsService;
  session: ActivePlanSessionState;

  constructor(opts?: WorkspaceOptions) {
    this.baseDir = ensureConfigDirectories(opts?.baseDir ?? getConfigDir());
    this.offlineOnly = opts?.offlineOnly ?? false;
    this.prefsMgr = new PreferencesManager(this.baseDir);
    this.radioMgr = new RadioManager(this.baseDir);
    this.templateMgr = new TemplateManager(this.baseDir);
    this.recipeMgr = new RecipeManager(this.baseDir);
    this.geocoder = new GeocodingProvider(this.offlineOnly);
    this.repeaterProvider = new RepeaterBookProvider({
      cacheDir: getCacheDir(this.baseDir),
      apiKey: this.prefsMgr.tokens.repeaterBookApiKey,
      maxAgeDays: this.prefsMgr.preferences.repeaterMaxAgeDays,
      offlineOnly: this.offlineOnly,
    });
    this.airportsProvider = new AirportsProvider();
    this.radioIdProvider = new RadioIdProvider(this.offlineOnly);
    this.lookupService = new CallsignLookupService(
      this.prefsMgr.tokens.qrzUsername,
      this.prefsMgr.tokens.qrzPassword,
    );
    this.nwsService = new NwsAlertsService(this.offlineOnly);
    this.session = new ActivePlanSessionState();

    if (opts?.loadPersistedSession !== false) {
      this.loadSession();
    }
  }

  sessionFilePath(): string {
    return getSessionFile(this.baseDir);
  }

  saveSession(): boolean {
    const filePath = this.sessionFilePath();
    try {
      fs.mkdirSync(path.dirname(filePath), { recursive: true });
      fs.writeFileSync(filePath, JSON.stringify(this.session.toPersistedDict(), null, 2), "utf-8");
      return true;
    } catch {
      return false;
    }
  }

  loadSession(): boolean {
    const filePath = this.sessionFilePath();
    if (!fs.existsSync(filePath)) return false;
    try {
      const parsed = JSON.parse(fs.readFileSync(filePath, "utf-8"));
      const restored = ActivePlanSessionState.fromPersistedDict(parsed);
      if (restored.codeplug) {
        this.session = restored;
        return true;
      }
    } catch {
      // Ignore corrupt session
    }
    return false;
  }

  reloadAll(): void {
    ensureConfigDirectories(this.baseDir);
    this.prefsMgr = new PreferencesManager(this.baseDir);
    this.radioMgr = new RadioManager(this.baseDir);
    this.templateMgr = new TemplateManager(this.baseDir);
    this.recipeMgr = new RecipeManager(this.baseDir);
    this.repeaterProvider.apiKey = this.prefsMgr.tokens.repeaterBookApiKey;
    this.repeaterProvider.lastStatus = this.prefsMgr.tokens.repeaterBookApiKey ? "CONFIGURED" : "NO_KEY";
    this.lookupService = new CallsignLookupService(
      this.prefsMgr.tokens.qrzUsername,
      this.prefsMgr.tokens.qrzPassword,
    );
  }
}
