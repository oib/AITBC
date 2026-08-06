// ts-jest was already a devDependency but nothing selected it, so jest fell back to
// babel-jest and failed to parse the first type annotation in tests/applyTheme.spec.ts --
// the suite had never run. The theme code reads window.matchMedia and localStorage, so it
// needs the jsdom environment rather than jest's default node one.
module.exports = {
  preset: "ts-jest",
  testEnvironment: "jsdom",
  testMatch: ["<rootDir>/tests/**/*.spec.ts", "<rootDir>/tests/**/*.spec.tsx"],
};
