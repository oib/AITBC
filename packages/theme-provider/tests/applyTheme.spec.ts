/**
 * Tests for theme application to the document element.
 *
 * Replaces packages/web/tests/visual/regression.spec.ts, which was called "visual
 * regression" but rendered nothing: it called `setAttribute` itself and then asserted
 * `getAttribute` returned what it had just set. That tests the DOM API, not the theme
 * system — it would have passed with theme-provider deleted entirely.
 *
 * These call the real `applyTheme` and assert on what it puts on the document. Modest,
 * but it fails if the theming breaks. A genuine visual-regression suite needs Playwright
 * and a built `packages/web`; that remains unbuilt rather than simulated (PKG-10).
 */

import { applyTheme, readStoredTheme } from "../src/no-fouc";

const THEME_ATTR = "data-aitbc-theme";
const STORAGE_KEY = "aitbc-theme-preference";

function setSystemPrefersDark(dark: boolean): void {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: query.includes("prefers-color-scheme: dark") ? dark : false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

describe("applyTheme", () => {
  beforeEach(() => {
    document.documentElement.removeAttribute(THEME_ATTR);
    localStorage.clear();
    setSystemPrefersDark(false);
  });

  it("applies an explicit dark mode", () => {
    applyTheme("dark");
    expect(document.documentElement.getAttribute(THEME_ATTR)).toBe("dark");
  });

  it("applies an explicit light mode", () => {
    applyTheme("light");
    expect(document.documentElement.getAttribute(THEME_ATTR)).toBe("light");
  });

  it("resolves system mode to dark when the OS prefers dark", () => {
    setSystemPrefersDark(true);
    applyTheme("system");
    expect(document.documentElement.getAttribute(THEME_ATTR)).toBe("dark");
  });

  it("resolves system mode to light when the OS prefers light", () => {
    setSystemPrefersDark(false);
    applyTheme("system");
    expect(document.documentElement.getAttribute(THEME_ATTR)).toBe("light");
  });

  it("overwrites a previously applied theme rather than accumulating", () => {
    applyTheme("dark");
    applyTheme("light");
    expect(document.documentElement.getAttribute(THEME_ATTR)).toBe("light");
  });
});

describe("readStoredTheme", () => {
  beforeEach(() => {
    localStorage.clear();
    delete (window as unknown as Record<string, unknown>).__AITBC_THEME__;
  });

  it("returns null when nothing is stored", () => {
    expect(readStoredTheme()).toBeNull();
  });

  it("reads the JSON object ThemeProvider actually writes", () => {
    // The regression: ThemeProvider persists the whole preference object, and this used
    // to be read as a bare string, so the literal JSON was returned as a theme mode and
    // applied to the document.
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ mode: "dark", reducedMotion: false, highContrast: false }),
    );
    expect(readStoredTheme()).toBe("dark");
  });

  it("still reads a legacy bare mode string", () => {
    localStorage.setItem(STORAGE_KEY, "light");
    expect(readStoredTheme()).toBe("light");
  });

  it("returns null for a value that is not a valid mode", () => {
    localStorage.setItem(STORAGE_KEY, "not json");
    expect(readStoredTheme()).toBeNull();
  });

  it("returns null for JSON carrying an unknown mode", () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ mode: "chartreuse" }));
    expect(readStoredTheme()).toBeNull();
  });
});

describe("no-FOUC bootstrap end to end", () => {
  beforeEach(() => {
    document.documentElement.removeAttribute(THEME_ATTR);
    localStorage.clear();
    setSystemPrefersDark(false);
  });

  it("applies the stored mode, not the raw stored value", () => {
    // Writing what ThemeProvider writes, then bootstrapping, must yield a usable theme
    // name -- never the serialized object, which matches no CSS selector.
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ mode: "dark", reducedMotion: false, highContrast: false }),
    );
    applyTheme(readStoredTheme() ?? "system");

    const applied = document.documentElement.getAttribute(THEME_ATTR);
    expect(applied).toBe("dark");
    expect(applied).not.toContain("{");
  });
});
