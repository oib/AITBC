/** Same jsdom stack as packages/web — tests live under website/tests/. */
module.exports = {
  testEnvironment: 'jsdom',
  testMatch: ['<rootDir>/tests/**/*.test.js'],
  rootDir: __dirname,
};
