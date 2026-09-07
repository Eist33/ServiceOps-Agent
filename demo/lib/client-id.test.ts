import assert from 'node:assert/strict';
import test from 'node:test';

import { clientId } from './client-id.ts';

test('clientId uses a native UUID when the browser exposes it', () => {
  const value = clientId('native');
  assert.match(value, /^native-[0-9a-f-]{36}$/);
});

test('clientId has a local fallback for insecure Docker browser origins', () => {
  const originalCrypto = globalThis.crypto;
  Object.defineProperty(globalThis, 'crypto', {
    configurable: true,
    value: {
      getRandomValues(values: Uint32Array) {
        values[0] = 123;
        values[1] = 456;
        return values;
      },
    },
  });
  try {
    const first = clientId('fallback');
    const second = clientId('fallback');
    assert.match(first, /^fallback-[a-z0-9]+-\d+-[a-z0-9]+$/);
    assert.notEqual(first, second);
  } finally {
    Object.defineProperty(globalThis, 'crypto', {
      configurable: true,
      value: originalCrypto,
    });
  }
});
