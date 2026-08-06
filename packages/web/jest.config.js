// Same ts-jest/jsdom setup as @aitbc/theme-provider.
//
// passWithNoTests is deliberate and temporary: this package currently has no test files
// at all. Rendering its components needs react/react-dom (declared only as peer
// dependencies here) plus a testing library, which is a separate piece of work. The flag
// makes that gap explicit rather than leaving `pnpm -r run test` failing for a reason
// unrelated to code quality -- when tests land, remove it.
module.exports = {
  preset: "ts-jest",
  testEnvironment: "jsdom",
  passWithNoTests: true,
  testMatch: ["<rootDir>/tests/**/*.spec.ts", "<rootDir>/tests/**/*.spec.tsx"],
};
