import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  clearLocalXianyuExperimentData,
  clearLocalXianyuPageCaches,
} from './xianyu-local-lifecycle.ts';
import { XIANYU_CHAT_DETAIL_STORAGE_KEY } from './xianyu-chat-detail.ts';
import { XIANYU_CHAT_LIST_STORAGE_KEY } from './xianyu-chat-list.ts';
import { XIANYU_CONNECTION_STORAGE_KEY } from './xianyu-local-session.ts';

function installMemorySessionStorage() {
  const values = new Map<string, string>();
  const sessionStorage = {
    getItem(key: string) {
      return values.get(key) ?? null;
    },
    setItem(key: string, value: string) {
      values.set(key, value);
    },
    removeItem(key: string) {
      values.delete(key);
    },
  } as unknown as Storage;
  Object.assign(globalThis, { window: { sessionStorage } });
  return sessionStorage;
}

void test('clear page caches keeps connection state and is idempotent', () => {
  const sessionStorage = installMemorySessionStorage();
  sessionStorage.setItem(XIANYU_CONNECTION_STORAGE_KEY, 'connection');
  sessionStorage.setItem(XIANYU_CHAT_LIST_STORAGE_KEY, 'chat-list');
  sessionStorage.setItem(XIANYU_CHAT_DETAIL_STORAGE_KEY, 'chat-detail');

  clearLocalXianyuPageCaches();
  clearLocalXianyuPageCaches();

  assert.equal(
    sessionStorage.getItem(XIANYU_CONNECTION_STORAGE_KEY),
    'connection',
  );
  assert.equal(sessionStorage.getItem(XIANYU_CHAT_LIST_STORAGE_KEY), null);
  assert.equal(sessionStorage.getItem(XIANYU_CHAT_DETAIL_STORAGE_KEY), null);
});

void test('clear experiment data removes every owned key without affecting another tab', () => {
  const firstTabStorage = installMemorySessionStorage();
  firstTabStorage.setItem(XIANYU_CONNECTION_STORAGE_KEY, 'connection-a');
  firstTabStorage.setItem(XIANYU_CHAT_LIST_STORAGE_KEY, 'chat-list-a');
  firstTabStorage.setItem(XIANYU_CHAT_DETAIL_STORAGE_KEY, 'chat-detail-a');

  const secondTabStorage = installMemorySessionStorage();
  secondTabStorage.setItem(XIANYU_CONNECTION_STORAGE_KEY, 'connection-b');
  secondTabStorage.setItem(XIANYU_CHAT_LIST_STORAGE_KEY, 'chat-list-b');
  secondTabStorage.setItem(XIANYU_CHAT_DETAIL_STORAGE_KEY, 'chat-detail-b');

  Object.assign(globalThis, { window: { sessionStorage: firstTabStorage } });
  clearLocalXianyuExperimentData();
  clearLocalXianyuExperimentData();

  assert.equal(firstTabStorage.getItem(XIANYU_CONNECTION_STORAGE_KEY), null);
  assert.equal(firstTabStorage.getItem(XIANYU_CHAT_LIST_STORAGE_KEY), null);
  assert.equal(firstTabStorage.getItem(XIANYU_CHAT_DETAIL_STORAGE_KEY), null);
  assert.equal(
    secondTabStorage.getItem(XIANYU_CONNECTION_STORAGE_KEY),
    'connection-b',
  );
  assert.equal(
    secondTabStorage.getItem(XIANYU_CHAT_LIST_STORAGE_KEY),
    'chat-list-b',
  );
  assert.equal(
    secondTabStorage.getItem(XIANYU_CHAT_DETAIL_STORAGE_KEY),
    'chat-detail-b',
  );
});
