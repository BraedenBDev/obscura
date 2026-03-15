export default {
  testEnvironment: 'jsdom',
  setupFilesAfterEnv: ['<rootDir>/tests/unit/setup.js'],
  testMatch: ['**/tests/unit/**/*.test.js'],
  moduleFileExtensions: ['js', 'json'],
  transform: {},
  injectGlobals: true,
  collectCoverageFrom: [
    'src/**/*.js',
    '!src/**/*.test.js'
  ],
  coverageThreshold: {
    global: {
      branches: 80,
      functions: 80,
      lines: 80,
      statements: 80
    }
  }
};
