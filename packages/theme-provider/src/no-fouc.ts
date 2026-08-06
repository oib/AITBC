/**
 * No-FOUC (Flash of Unstyled Content) helper.
 *
 * Reads the stored theme preference and applies it synchronously before the
 * React hydration pass. When running in a browser with Redis-cached server
 * preferences, the preference may be injected as a global window variable
 * `__AITBC_THEME__`.
 */

export type ThemeMode = "system" | "light" | "dark" | "high-contrast";

const STORAGE_KEY = "aitbc-theme-preference";

function resolveThemeMode(stored: ThemeMode | null, systemPrefersDark: boolean): ThemeMode {
  if (stored && stored !== "system") {
    return stored;
  }
  return systemPrefersDark ? "dark" : "light";
}

/** Apply the resolved theme to the document element immediately. */
export function applyTheme(mode: ThemeMode): void {
  const resolved =
    mode === "system"
      ? window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : mode;

  document.documentElement.setAttribute("data-aitbc-theme", resolved);
}

/** Read the persisted theme preference. */
const VALID_MODES: readonly string[] = ["system", "light", "dark", "high-contrast"];

function coerceMode(raw: string | null): ThemeMode | null {
  if (!raw) return null;
  // ThemeProvider persists the whole preference object as JSON under this key. Reading it
  // as a bare string returned the literal '{"mode":"dark",...}' and treated it as a theme
  // name, so applyTheme wrote that blob into data-aitbc-theme, no CSS selector matched,
  // and the no-FOUC bootstrap produced exactly the flash of wrong theme it exists to
  // prevent. Parse the object form first, and accept a bare mode for older stored values.
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && typeof parsed.mode === "string") {
      return VALID_MODES.includes(parsed.mode) ? (parsed.mode as ThemeMode) : null;
    }
  } catch {
    // not JSON — fall through to the legacy bare-string form
  }
  return VALID_MODES.includes(raw) ? (raw as ThemeMode) : null;
}

export function readStoredTheme(): ThemeMode | null {
  try {
    // Set by the server-rendered inline script, so it is not on the standard Window type.
    const server = (window as Window & { __AITBC_THEME__?: ThemeMode }).__AITBC_THEME__;
    if (server) return VALID_MODES.includes(server) ? server : null;
    return coerceMode(window.localStorage.getItem(STORAGE_KEY));
  } catch {
    return null;
  }
}

/** Synchronous no-FOUC bootstrap. Call in a `<script>` in `<head>`. */
export function injectNoFOUC(): void {
  const stored = readStoredTheme();
  const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const resolved = resolveThemeMode(stored, systemDark);
  applyTheme(resolved);
}

/** Inline-safe version for embedding in HTML. */
export const NOFOUCScript = `
(function(){
  try {
    var valid = ["system","light","dark","high-contrast"];
    var raw = window.__AITBC_THEME__ || localStorage.getItem("${STORAGE_KEY}");
    var stored = null;
    if (raw) {
      // ThemeProvider stores the preference object as JSON; older values may be a bare
      // mode string. Reading the JSON as a mode wrote the whole blob into the attribute,
      // matching no CSS rule and causing the exact flash this script prevents.
      try {
        var parsed = JSON.parse(raw);
        if (parsed && typeof parsed === "object" && valid.indexOf(parsed.mode) !== -1) {
          stored = parsed.mode;
        }
      } catch (e) {
        if (valid.indexOf(raw) !== -1) stored = raw;
      }
      if (!stored && valid.indexOf(raw) !== -1) stored = raw;
    }
    var dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    var mode = stored || (dark ? "dark" : "light");
    if (mode === "system") mode = dark ? "dark" : "light";
    document.documentElement.setAttribute("data-aitbc-theme", mode);
  } catch (e) {}
})();
`;
