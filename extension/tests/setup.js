// tests/setup.js
// Chrome API mock for testing

import { mock } from 'bun:test';

// Create chrome storage mock
const mockStorage = {
  local: {
    get: mock((keys, callback) => {
      if (callback) callback({});
      return Promise.resolve({});
    }),
    set: mock((data, callback) => {
      if (callback) callback();
      return Promise.resolve();
    }),
    remove: mock((keys, callback) => {
      if (callback) callback();
      return Promise.resolve();
    }),
    clear: mock((callback) => {
      if (callback) callback();
      return Promise.resolve();
    })
  },
  sync: {
    get: mock((keys, callback) => {
      if (callback) callback({});
      return Promise.resolve({});
    }),
    set: mock((data, callback) => {
      if (callback) callback();
      return Promise.resolve();
    })
  }
};

// Create chrome runtime mock
const mockRuntime = {
  sendMessage: mock((message, callback) => {
    if (callback) callback({});
    return Promise.resolve({});
  }),
  onMessage: {
    addListener: mock(() => {}),
    removeListener: mock(() => {})
  },
  getURL: mock((path) => `chrome-extension://mock-id/${path}`),
  id: 'mock-extension-id'
};

// Create chrome tabs mock
const mockTabs = {
  query: mock((queryInfo, callback) => {
    if (callback) callback([]);
    return Promise.resolve([]);
  }),
  sendMessage: mock((tabId, message, callback) => {
    if (callback) callback({});
    return Promise.resolve({});
  }),
  create: mock((createProperties, callback) => {
    const tab = { id: 1, ...createProperties };
    if (callback) callback(tab);
    return Promise.resolve(tab);
  })
};

// Create chrome identity mock
const mockIdentity = {
  getAuthToken: mock((options, callback) => {
    if (callback) callback('mock-token');
    return Promise.resolve('mock-token');
  })
};

// Create full chrome mock
globalThis.chrome = {
  storage: mockStorage,
  runtime: mockRuntime,
  tabs: mockTabs,
  identity: mockIdentity
};

export { mockStorage, mockRuntime, mockTabs, mockIdentity };
