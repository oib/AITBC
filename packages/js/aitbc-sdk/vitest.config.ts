import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    reporters: ['verbose', 'junit'],
    outputFile: {
      junit: './test-results/junit.xml'
    },
    coverage: {
      reporter: ['text', 'json', 'html'],
      reportsDirectory: './test-results/coverage',
    },
  },
});
