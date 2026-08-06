import { useAitbcTheme } from "@aitbc/theme-provider";

export interface AitbcPreferences {
  mode: "system" | "light" | "dark" | "high-contrast";
  reducedMotion: boolean;
  highContrast: boolean;
}

/**
 * Theme preferences, delegating to the ThemeProvider context.
 *
 * This hook used to own `localStorage["aitbc-theme-preference"]` itself, in parallel with
 * ThemeProvider (and no-fouc.ts) — three independent owners of one key, each with its own
 * React state and no `storage` event listener. With both mounted, and `@aitbc/web` depends
 * on `@aitbc/theme-provider` so that is the normal case, a write through one was invisible
 * to the other until a reload: toggling in AppearancePanel left anything reading through
 * this hook showing stale values.
 *
 * There is now a single owner. This is a thin adapter over `useAitbcTheme` kept for API
 * compatibility; prefer `useAitbcTheme` directly in new code.
 *
 * Must be called within a ThemeProvider — `useAitbcTheme` throws otherwise, which is a
 * clearer failure than silently diverging state.
 */
export function usePreferences(): {
  preferences: AitbcPreferences;
  setPreferences: (prefs: Partial<AitbcPreferences>) => void;
} {
  const { preference, setMode, setReducedMotion, setHighContrast } = useAitbcTheme();

  const preferences: AitbcPreferences = {
    mode: preference.mode as AitbcPreferences["mode"],
    reducedMotion: preference.reducedMotion,
    highContrast: preference.highContrast,
  };

  const setPreferences = (prefs: Partial<AitbcPreferences>) => {
    // Applied through the provider so every consumer re-renders and storage is written
    // once, by its owner.
    if (prefs.mode !== undefined) setMode(prefs.mode as never);
    if (prefs.reducedMotion !== undefined) setReducedMotion(prefs.reducedMotion);
    if (prefs.highContrast !== undefined) setHighContrast(prefs.highContrast);
  };

  return { preferences, setPreferences };
}
