import { jest, beforeEach } from '@jest/globals';
import { chrome } from 'jest-chrome';

// Make chrome globally available
global.chrome = chrome;

// Default mock implementations
chrome.storage.local.get.mockImplementation((keys, callback) => {
  const result = {};
  if (typeof keys === 'string') {
    result[keys] = undefined;
  } else if (Array.isArray(keys)) {
    keys.forEach(k => result[k] = undefined);
  }
  if (callback) callback(result);
  return Promise.resolve(result);
});

chrome.storage.local.set.mockImplementation((data, callback) => {
  if (callback) callback();
  return Promise.resolve();
});

chrome.storage.sync.get.mockImplementation((keys, callback) => {
  const result = {};
  if (callback) callback(result);
  return Promise.resolve(result);
});

chrome.storage.sync.set.mockImplementation((data, callback) => {
  if (callback) callback();
  return Promise.resolve();
});

chrome.runtime.sendMessage.mockImplementation((msg, callback) => {
  if (callback) callback({});
  return Promise.resolve({});
});

// Reset mocks between tests
beforeEach(() => {
  jest.clearAllMocks();
});
