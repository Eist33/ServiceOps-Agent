import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  XIANYU_CONNECTION_STORAGE_KEY,
  XIANYU_LOCAL_PAGE_VERSION,
  clearLocalXianyuConnection,
  createLocalXianyuConnection,
  markXianyuReauthRequired,
  parseLocalXianyuConnection,
  readLocalXianyuConnection,
  subscribeLocalXianyuConnection,
  writeLocalXianyuConnection,
} from './xianyu-local-session.ts';

const NOW = '2026-09-05T10:00:00.000Z';

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
  };
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: { sessionStorage },
  });
  return sessionStorage;
}

void test('local connection output contains only fixed-page metadata', () => {
  const connection = createLocalXianyuConnection('account-a', {
    consentedAt: NOW,
    now: NOW,
  });

  assert.equal(connection.provider, 'XIANYU');
  assert.equal(connection.display_identifier, '本地模拟账号 A');
  assert.equal(connection.source_page_version, XIANYU_LOCAL_PAGE_VERSION);
  assert.equal(connection.status, 'CONNECTED');
  assert.match(connection.connection_id, /^[0-9a-f-]{36}$/);

  const serialized = JSON.stringify(connection).toLowerCase();
  for (const forbidden of [
    '手机号',
    '验证码',
    'cookie',
    'token',
    'serviceops',
  ]) {
    assert.equal(serialized.includes(forbidden), false, forbidden);
  }
});

void test('unknown or changed page metadata fails closed', () => {
  const connection = createLocalXianyuConnection('account-a', { now: NOW });
  const invalidPayloads = [
    'not-json',
    JSON.stringify({ ...connection, provider: 'TAOBAO' }),
    JSON.stringify({ ...connection, source_page_version: 'page-v2' }),
    JSON.stringify({ ...connection, display_identifier: '林沐' }),
    JSON.stringify({ ...connection, token: 'secret-token' }),
    JSON.stringify({
      ...connection,
      status: 'CONNECTED',
      last_synced_at: 'unknown',
    }),
  ];

  for (const payload of invalidPayloads) {
    assert.equal(parseLocalXianyuConnection(payload), null);
  }
});

void test('reauthentication is an explicit fail-closed state transition', () => {
  const connection = createLocalXianyuConnection('account-a', { now: NOW });
  const invalidated = markXianyuReauthRequired(connection);

  assert.equal(connection.status, 'CONNECTED');
  assert.equal(invalidated.status, 'REAUTH_REQUIRED');
  assert.equal(invalidated.connection_id, connection.connection_id);
  assert.throws(
    () => markXianyuReauthRequired(invalidated),
    /已经处于重新登录状态/,
  );
});

void test('session storage round trip, invalidation cleanup, and exit cleanup are local', () => {
  const sessionStorage = installMemorySessionStorage();
  const connection = createLocalXianyuConnection('account-b', { now: NOW });
  let notifications = 0;
  const unsubscribe = subscribeLocalXianyuConnection(() => {
    notifications += 1;
  });

  writeLocalXianyuConnection(connection);
  assert.deepEqual(readLocalXianyuConnection(), connection);
  assert.equal(notifications, 1);

  sessionStorage.setItem(
    XIANYU_CONNECTION_STORAGE_KEY,
    JSON.stringify({ ...connection, token: 'secret-token' }),
  );
  assert.equal(readLocalXianyuConnection(), null);
  assert.equal(sessionStorage.getItem(XIANYU_CONNECTION_STORAGE_KEY), null);

  writeLocalXianyuConnection(connection);
  clearLocalXianyuConnection();
  assert.equal(sessionStorage.getItem(XIANYU_CONNECTION_STORAGE_KEY), null);
  assert.equal(notifications, 3);
  unsubscribe();
});
