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
export function readStoredTheme(): ThemeMode | null {
  try {
    const server = (window as any).__AITBC_THEME__ as ThemeMode | undefined;
    if (server) return server;
    return window.localStorage.getItem(STORAGE_KEY) as ThemeMode | null;
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
    var stored = window.__AITBC_THEME__ || localStorage.getItem("${STORAGE_KEY}");
    var dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    var mode = stored || (dark ? "dark" : "light");
    if (mode === "system") mode = dark ? "dark" : "light";
    document.documentElement.setAttribute("data-aitbc-theme", mode);
  } catch (e) {}
})();
`;
