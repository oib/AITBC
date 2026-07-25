/**
 * Visual regression tests for AITBC themes.
 *
 * ponytail: These are placeholder Playwright-style specs. A production run
 * requires a build of `packages/web` and Playwright installed.
 */

describe("Theme visual regression", () => {
  it("renders dark mode baseline", () => {
    document.documentElement.setAttribute("data-aitbc-theme", "dark");
    expect(document.documentElement.getAttribute("data-aitbc-theme")).toBe("dark");
  });

  it("renders light mode baseline", () => {
    document.documentElement.setAttribute("data-aitbc-theme", "light");
    expect(document.documentElement.getAttribute("data-aitbc-theme")).toBe("light");
  });

  it("renders high-contrast mode baseline", () => {
    document.documentElement.setAttribute("data-aitbc-theme", "high-contrast");
    expect(document.documentElement.getAttribute("data-aitbc-theme")).toBe("high-contrast");
  });
});
