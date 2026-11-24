/**
 * Configuration Managers: RadioManager, TemplateManager, PreferencesManager, and RecipeManager.
 * All user-editable files are clean YAML stored under %APPDATA%\W5CDN\RadioPlanner (or RADIOPLANNER_HOME),
 * supporting hand-edit export (.yaml) and strict validated YAML import.
 */

import fs from "node:fs";
import path from "node:path";
import { safeChildPath, sanitizeFilename, sanitizeSlug } from "../shared/sanitize";
import {
  ApiTokens,
  PresetTemplateFile,
  RadioChannel,
  RadioPlannerRecipe,
  TargetRadioSpec,
  UserPreferences,
  templateFileToRadioChannels,
} from "../shared/types";
import {
  YamlDiagnosticError,
  defaultApiTokens,
  defaultUserPreferences,
  dumpYamlText,
  loadYamlFile,
  normalizeApiTokens,
  normalizeUserPreferences,
  parseYamlText,
  validateRadioSpec,
  validateRecipe,
  validateTemplateFile,
} from "../shared/yamlDiagnostics";
import {
  ensureConfigDirectories,
  getConfigDir,
  getPreferencesFile,
  getTokensFile,
  getUserRadiosDir,
  getUserRecipesDir,
  getUserTemplatesDir,
  readSharedSuiteConfig,
  resolveResourcesDir,
} from "./paths";

export class RadioManager {
  readonly builtinDir: string;
  readonly userDir: string;
  private radios = new Map<string, TargetRadioSpec>();
  private userIds = new Set<string>();

  constructor(baseDir = getConfigDir()) {
    this.builtinDir = path.join(resolveResourcesDir(), "radios");
    this.userDir = getUserRadiosDir(baseDir);
    this.reload();
  }

  reload(): void {
    this.radios.clear();
    this.userIds.clear();
    this.loadDirectory(this.builtinDir, false);
    this.loadDirectory(this.userDir, true);
  }

  private loadDirectory(dir: string, isUser: boolean): void {
    if (!fs.existsSync(dir)) return;
    const files = fs
      .readdirSync(dir)
      .filter((f) => f.toLowerCase().endsWith(".yaml") || f.toLowerCase().endsWith(".yml"))
      .sort();
    for (const file of files) {
      const fullPath = path.join(dir, file);
      try {
        const raw = loadYamlFile(fullPath);
        const spec = validateRadioSpec(raw, fullPath);
        this.radios.set(spec.id, spec);
        if (isUser) this.userIds.add(spec.id);
      } catch {
        // Ignore invalid radio file on startup so one bad file doesn't break the app
      }
    }
  }

  listRadios(): TargetRadioSpec[] {
    return Array.from(this.radios.values()).sort((a, b) =>
      `${a.brand} ${a.model}`.localeCompare(`${b.brand} ${b.model}`),
    );
  }

  hasRadio(id: string): boolean {
    return this.radios.has(id);
  }

  isUserRadio(id: string): boolean {
    return this.userIds.has(id);
  }

  getRadio(id: string): TargetRadioSpec {
    const spec = this.radios.get(id);
    if (!spec) {
      throw new Error(`Radio specification '${id}' not found.`);
    }
    return spec;
  }

  exportRadioYaml(id: string): { filename: string; yaml: string } {
    const spec = this.getRadio(id);
    const header = [
      `W5CDN RadioPlanner — Radio Hardware Profile (${spec.brand} ${spec.model})`,
      "Edit this YAML file carefully, then re-import it in RadioPlanner's Radios panel.",
      "Supported programmerType values: CHIRP, RT_SYSTEMS, VENDOR_CPS, GENERIC_CSV",
    ].join("\n");
    return {
      filename: `${sanitizeSlug(spec.id, "radio")}.yaml`,
      yaml: dumpYamlText(spec, header),
    };
  }

  importRadioYaml(yamlText: string, sourceLabel = "imported_radio.yaml"): TargetRadioSpec {
    const raw = parseYamlText(yamlText, sourceLabel);
    const spec = validateRadioSpec(raw, sourceLabel);
    this.saveUserRadio(spec);
    return spec;
  }

  saveUserRadio(spec: TargetRadioSpec): string {
    fs.mkdirSync(this.userDir, { recursive: true });
    const filename = `${sanitizeSlug(spec.id, "custom_radio")}.yaml`;
    const dest = safeChildPath(this.userDir, filename);
    const content = dumpYamlText(
      spec,
      `W5CDN RadioPlanner — User Radio Profile (${spec.brand} ${spec.model})`,
    );
    fs.writeFileSync(dest, content, "utf-8");
    this.radios.set(spec.id, spec);
    this.userIds.add(spec.id);
    return dest;
  }

  deleteUserRadio(id: string): boolean {
    if (!this.userIds.has(id)) return false;
    const filename = `${sanitizeSlug(id, "custom_radio")}.yaml`;
    const target = safeChildPath(this.userDir, filename);
    if (fs.existsSync(target)) {
      fs.unlinkSync(target);
    }
    this.reload();
    return true;
  }
}

export class TemplateManager {
  readonly appDir: string;
  readonly userDir: string;
  private templates = new Map<string, PresetTemplateFile>();
  private userIds = new Set<string>();

  constructor(baseDir = getConfigDir()) {
    this.appDir = path.join(resolveResourcesDir(), "templates");
    this.userDir = getUserTemplatesDir(baseDir);
    this.reload();
  }

  reload(): void {
    this.templates.clear();
    this.userIds.clear();
    this.loadDirectory(this.appDir, false);
    this.loadDirectory(this.userDir, true);
  }

  private loadDirectory(dir: string, isUser: boolean): void {
    if (!fs.existsSync(dir)) return;
    const files = fs
      .readdirSync(dir)
      .filter((f) => f.toLowerCase().endsWith(".yaml") || f.toLowerCase().endsWith(".yml"))
      .sort();
    for (const file of files) {
      const fullPath = path.join(dir, file);
      try {
        const raw = loadYamlFile(fullPath);
        const tpl = validateTemplateFile({ ...raw, fileName: file }, fullPath);
        this.templates.set(tpl.id, tpl);
        if (isUser) this.userIds.add(tpl.id);
      } catch {
        // Ignore broken template file on startup
      }
    }
  }

  listTemplates(): PresetTemplateFile[] {
    return Array.from(this.templates.values()).sort((a, b) => a.name.localeCompare(b.name));
  }

  hasTemplate(id: string): boolean {
    return this.templates.has(id);
  }

  isUserTemplate(id: string): boolean {
    return this.userIds.has(id);
  }

  getTemplate(id: string): PresetTemplateFile {
    const tpl = this.templates.get(id);
    if (!tpl) {
      throw new Error(`Template '${id}' not found.`);
    }
    return tpl;
  }

  getTemplateChannels(id: string): RadioChannel[] {
    const tpl = this.templates.get(id);
    if (!tpl) return [];
    return templateFileToRadioChannels(tpl);
  }

  exportTemplateYaml(id: string): { filename: string; yaml: string } {
    const tpl = this.getTemplate(id);
    const cleanPayload = {
      id: tpl.id,
      name: tpl.name,
      description: tpl.description,
      tagText: tpl.tagText,
      tagColorHex: tpl.tagColorHex,
      channels: tpl.channels,
    };
    const header = [
      `W5CDN RadioPlanner — Channel Template (${tpl.name})`,
      "Edit channels carefully, then re-import via the Templates panel.",
    ].join("\n");
    return {
      filename: `${sanitizeSlug(tpl.id, "template")}.yaml`,
      yaml: dumpYamlText(cleanPayload, header),
    };
  }

  saveTemplate(tpl: PresetTemplateFile): string {
    fs.mkdirSync(this.userDir, { recursive: true });
    const filename = `${sanitizeSlug(tpl.id, "custom_template")}.yaml`;
    const dest = safeChildPath(this.userDir, filename);
    const cleanPayload = {
      id: tpl.id,
      name: tpl.name,
      description: tpl.description,
      tagText: tpl.tagText,
      tagColorHex: tpl.tagColorHex,
      channels: tpl.channels,
    };
    fs.writeFileSync(
      dest,
      dumpYamlText(cleanPayload, `W5CDN RadioPlanner — Channel Template (${tpl.name})`),
      "utf-8",
    );
    this.templates.set(tpl.id, { ...tpl, fileName: filename });
    this.userIds.add(tpl.id);
    return dest;
  }

  deleteTemplate(id: string): boolean {
    if (!this.userIds.has(id)) return false;
    const filename = `${sanitizeSlug(id, "custom_template")}.yaml`;
    const target = safeChildPath(this.userDir, filename);
    if (fs.existsSync(target)) {
      fs.unlinkSync(target);
    }
    this.reload();
    return true;
  }
}

export class PreferencesManager {
  readonly baseDir: string;
  readonly prefsFile: string;
  readonly tokensFile: string;
  preferences: UserPreferences;
  tokens: ApiTokens;

  constructor(baseDir = getConfigDir()) {
    this.baseDir = ensureConfigDirectories(baseDir);
    this.prefsFile = getPreferencesFile(this.baseDir);
    this.tokensFile = getTokensFile(this.baseDir);
    this.preferences = this.loadPreferences();
    this.tokens = this.loadTokens();
  }

  loadPreferences(): UserPreferences {
    let prefs = defaultUserPreferences();
    if (fs.existsSync(this.prefsFile)) {
      try {
        const raw = loadYamlFile(this.prefsFile);
        prefs = normalizeUserPreferences(raw);
      } catch {
        prefs = defaultUserPreferences();
      }
    }
    // Fall back to shared W5CDN Suite config.txt for operator callsign if still N0CALL
    if (prefs.callsign === "N0CALL") {
      const shared = readSharedSuiteConfig();
      const opCall = (shared.OPERATOR_CALL || shared.CALLSIGN || "").trim().toUpperCase();
      if (opCall) {
        prefs = { ...prefs, callsign: opCall };
      }
    }
    this.preferences = prefs;
    return prefs;
  }

  savePreferences(next: UserPreferences): void {
    fs.mkdirSync(path.dirname(this.prefsFile), { recursive: true });
    const normalized = normalizeUserPreferences(next as unknown as Record<string, unknown>);
    const content = dumpYamlText(
      normalized,
      "W5CDN RadioPlanner — User Preferences (safe to hand-edit when app is closed)",
    );
    fs.writeFileSync(this.prefsFile, content, "utf-8");
    this.preferences = normalized;
  }

  loadTokens(): ApiTokens {
    let tokens = defaultApiTokens();
    if (fs.existsSync(this.tokensFile)) {
      try {
        const raw = loadYamlFile(this.tokensFile);
        tokens = normalizeApiTokens(raw);
      } catch {
        tokens = defaultApiTokens();
      }
    }
    // Shared W5CDN suite QRZ fallback if not set in local tokens
    if (!tokens.qrzUsername || !tokens.qrzPassword) {
      const shared = readSharedSuiteConfig();
      tokens = {
        ...tokens,
        qrzUsername: tokens.qrzUsername || shared.QRZ_USER || null,
        qrzPassword: tokens.qrzPassword || shared.QRZ_PASS || null,
      };
    }
    this.tokens = tokens;
    return tokens;
  }

  saveTokens(next: ApiTokens): void {
    fs.mkdirSync(path.dirname(this.tokensFile), { recursive: true });
    const normalized = normalizeApiTokens(next as unknown as Record<string, unknown>);
    const content = dumpYamlText(normalized, "W5CDN RadioPlanner — API Credentials (local only, never share)");
    fs.writeFileSync(this.tokensFile, content, "utf-8");
    if (process.platform !== "win32") {
      try {
        fs.chmodSync(this.tokensFile, 0o600);
      } catch {
        // Best effort
      }
    }
    this.tokens = normalized;
  }
}

export class RecipeManager {
  readonly recipesDir: string;

  constructor(baseDir = getConfigDir()) {
    this.recipesDir = getUserRecipesDir(baseDir);
    fs.mkdirSync(this.recipesDir, { recursive: true });
  }

  listRecipes(): Array<{ filename: string; recipe: RadioPlannerRecipe }> {
    fs.mkdirSync(this.recipesDir, { recursive: true });
    const files = fs
      .readdirSync(this.recipesDir)
      .filter((f) => f.toLowerCase().endsWith(".yaml") || f.toLowerCase().endsWith(".yml"))
      .sort();
    const out: Array<{ filename: string; recipe: RadioPlannerRecipe }> = [];
    for (const file of files) {
      const fullPath = path.join(this.recipesDir, file);
      try {
        const raw = loadYamlFile(fullPath);
        const rec = validateRecipe(raw, fullPath);
        out.push({ filename: file, recipe: rec });
      } catch {
        // Skip invalid recipe
      }
    }
    return out;
  }

  getRecipe(filename: string): { filename: string; recipe: RadioPlannerRecipe; rawYaml: string } {
    const target = safeChildPath(this.recipesDir, filename);
    if (!fs.existsSync(target)) {
      throw new Error(`Recipe file '${filename}' not found.`);
    }
    const rawYaml = fs.readFileSync(target, "utf-8");
    const raw = parseYamlText(rawYaml, target);
    const recipe = validateRecipe(raw, target);
    return { filename: path.basename(target), recipe, rawYaml };
  }

  saveRecipe(recipe: RadioPlannerRecipe, explicitFilename?: string): { filename: string; fullPath: string } {
    fs.mkdirSync(this.recipesDir, { recursive: true });
    let fname = explicitFilename ? sanitizeFilename(explicitFilename, "recipe") : `${sanitizeFilename(recipe.name, "recipe")}.yaml`;
    if (!fname.toLowerCase().endsWith(".yaml") && !fname.toLowerCase().endsWith(".yml")) {
      fname += ".yaml";
    }
    const dest = safeChildPath(this.recipesDir, fname);

    // Strip target-specific radio binding so recipes remain radio-agnostic
    const dumpObj = {
      ...recipe,
      radio_target: {
        include_simplex: recipe.radio_target.include_simplex,
        bands: recipe.radio_target.bands,
        modes: recipe.radio_target.modes,
        repeater_access: recipe.radio_target.repeater_access,
        naming_format: recipe.radio_target.naming_format,
      },
    };
    const yamlText = dumpYamlText(
      dumpObj,
      `W5CDN RadioPlanner — Replayable Plan Recipe (${recipe.name})`,
    );
    fs.writeFileSync(dest, yamlText, "utf-8");
    return { filename: path.basename(dest), fullPath: dest };
  }

  importRecipeYaml(yamlText: string, filename = "uploaded_recipe.yaml"): { filename: string; recipe: RadioPlannerRecipe } {
    const raw = parseYamlText(yamlText, filename);
    const recipe = validateRecipe(raw, filename);
    const saved = this.saveRecipe(recipe, filename || `${sanitizeFilename(recipe.name)}.yaml`);
    return { filename: saved.filename, recipe };
  }

  deleteRecipe(filename: string): boolean {
    const target = safeChildPath(this.recipesDir, filename);
    if (!fs.existsSync(target)) return false;
    fs.unlinkSync(target);
    return true;
  }
}

export { YamlDiagnosticError };
