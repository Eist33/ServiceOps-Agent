import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  XIANYU_CHAT_LIST_MAX,
  XIANYU_CHAT_LIST_MISSING_FIELD_LIMIT,
  XIANYU_CHAT_LIST_STORAGE_KEY,
  clearLocalXianyuChatList,
  getLocalXianyuChatPage,
  parseLocalXianyuChatListSnapshot,
  readLocalXianyuChatList,
  readStoredLocalXianyuChatList,
  subscribeLocalXianyuChatList,
  writeLocalXianyuChatList,
  type XianyuLocalChatPage,
  type XianyuLocalChatPageRow,
} from './xianyu-chat-list.ts';
import {
  createLocalXianyuConnection,
  markXianyuReauthRequired,
  type XianyuFixtureId,
} from './xianyu-local-session.ts';

const NOW = '2026-09-05T10:00:00.000Z';

function connected(fixtureId: XianyuFixtureId = 'account-a') {
  return createLocalXianyuConnection(fixtureId, { now: NOW });
}

function pageWith(
  fixtureId: XianyuFixtureId,
  conversations: readonly XianyuLocalChatPageRow[],
  overrides: Record<string, unknown> = {},
): XianyuLocalChatPage {
  return {
    ...getLocalXianyuChatPage(fixtureId),
    ...overrides,
    conversations,
  } as XianyuLocalChatPage;
}

function fullRow(
  conversationId: string,
  lastMessageAt = '2026-09-05T09:00:00.000Z',
): XianyuLocalChatPageRow {
  return {
    conversation_id: conversationId,
    avatar_ref: `avatar-${conversationId}`,
    nickname: `用户-${conversationId}`,
    last_message_summary: '固定页面测试消息',
    last_message_at: lastMessageAt,
    unread_count: 1,
    is_pinned: false,
    is_muted: false,
  };
}

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

void test('normal page maps fields, records read metadata, and stays credential-free', () => {
  const connection = connected();
  const page = getLocalXianyuChatPage('account-a');
  const pageWithIgnoredField = {
    ...page,
    conversations: page.conversations.map((conversation) => ({
      ...conversation,
      token: 'secret-token',
    })),
  };
  const result = readLocalXianyuChatList(connection, pageWithIgnoredField, {
    readAt: NOW,
  });

  assert.equal(result.result, 'SUCCESS');
  if (result.result !== 'SUCCESS') return;
  assert.equal(result.connection_id, connection.connection_id);
  assert.equal(result.source_page_version, 'local-fixed-page-v1');
  assert.equal(result.read_at, NOW);
  assert.deepEqual(
    result.conversations.map((item) => item.conversation_id),
    ['a-conv-1001', 'a-conv-1002', 'a-conv-1003', 'a-conv-1004', 'a-conv-1005'],
  );
  assert.equal(result.conversations[0]?.unread_count, 2);
  assert.equal(result.conversations[2]?.last_message_summary, null);
  assert.equal(result.conversations[2]?.avatar_ref, null);
  assert.equal(result.conversations[2]?.unread_count, null);
  assert.equal(result.missing_field_ratio, 3 / 35);
  assert.doesNotMatch(
    JSON.stringify(result),
    /手机号|验证码|cookie|token|serviceops/i,
  );
});

void test('empty page succeeds with an explicit empty result', () => {
  const result = readLocalXianyuChatList(
    connected(),
    pageWith('account-a', [], { has_more: false }),
    { readAt: NOW },
  );

  assert.deepEqual(result, {
    schema_version: 1,
    result: 'SUCCESS',
    connection_id: result.connection_id,
    source_page_version: 'local-fixed-page-v1',
    read_at: NOW,
    truncated: false,
    missing_field_ratio: 0,
    conversations: [],
  });
});

void test('pagination is explicitly truncated at 20 and sorting is stable', () => {
  const rows = Array.from({ length: 25 }, (_, index) =>
    fullRow(
      `bulk-${String(index).padStart(2, '0')}`,
      `2026-09-05T09:${String(index).padStart(2, '0')}:00.000Z`,
    ),
  );
  rows[24] = { ...rows[24], is_pinned: true };
  const result = readLocalXianyuChatList(
    connected(),
    pageWith('account-a', rows, { has_more: true }),
    { readAt: NOW },
  );

  assert.equal(result.result, 'SUCCESS');
  if (result.result !== 'SUCCESS') return;
  assert.equal(result.conversations.length, XIANYU_CHAT_LIST_MAX);
  assert.equal(result.truncated, true);
  assert.equal(result.conversations[0]?.conversation_id, 'bulk-24');
  assert.equal(result.conversations.at(-1)?.conversation_id, 'bulk-05');
});

void test('small field gaps become UNKNOWN/null and remain a successful read', () => {
  const rows = [
    fullRow('complete'),
    { ...fullRow('partial'), last_message_summary: null, unread_count: null },
    fullRow('complete-2'),
    fullRow('complete-3'),
  ];
  const result = readLocalXianyuChatList(
    connected(),
    pageWith('account-a', rows),
    { readAt: NOW },
  );

  assert.equal(result.result, 'SUCCESS');
  if (result.result !== 'SUCCESS') return;
  assert.equal(result.missing_field_ratio, 2 / 28);
  assert.equal(
    result.conversations.find((item) => item.conversation_id === 'partial')
      ?.last_message_summary,
    null,
  );
  assert.equal(
    result.conversations.find((item) => item.conversation_id === 'partial')
      ?.unread_count,
    null,
  );
  assert.ok(result.missing_field_ratio <= XIANYU_CHAT_LIST_MISSING_FIELD_LIMIT);
});

void test('coverage above the documented limit fails without a partial success', () => {
  const result = readLocalXianyuChatList(
    connected(),
    pageWith('account-a', [
      {
        conversation_id: 'mostly-unknown',
        avatar_ref: null,
        nickname: null,
        last_message_summary: null,
        last_message_at: null,
        unread_count: null,
        is_pinned: null,
        is_muted: null,
      },
    ]),
    { readAt: NOW },
  );

  assert.equal(result.result, 'FAILED');
  if (result.result !== 'FAILED') return;
  assert.equal(result.error_code, 'FIELD_COVERAGE_TOO_LOW');
  assert.equal(result.error_message, '闲鱼页面字段缺失过多，需要重新适配。');
  assert.equal('conversations' in result, false);
});

void test('page version or row shape changes fail closed', () => {
  const connection = connected();
  const malformedPage = readLocalXianyuChatList(connection, null, {
    readAt: NOW,
  });
  assert.equal(malformedPage.result, 'FAILED');
  if (malformedPage.result === 'FAILED') {
    assert.equal(malformedPage.error_code, 'PAGE_CHANGED');
  }

  const changedVersion = readLocalXianyuChatList(
    connection,
    pageWith('account-a', [], { source_page_version: 'local-fixed-page-v2' }),
    { readAt: NOW },
  );
  assert.equal(changedVersion.result, 'FAILED');
  if (changedVersion.result === 'FAILED') {
    assert.equal(changedVersion.error_code, 'PAGE_CHANGED');
    assert.equal(changedVersion.source_page_version, 'local-fixed-page-v2');
  }

  const malformedRow = readLocalXianyuChatList(
    connection,
    pageWith('account-a', [{ ...fullRow('bad-id'), conversation_id: '   ' }]),
    { readAt: NOW },
  );
  assert.equal(malformedRow.result, 'FAILED');
  if (malformedRow.result === 'FAILED') {
    assert.equal(malformedRow.error_code, 'PAGE_CHANGED');
  }
});

void test('page ownership is required even when two fixtures share a nickname', () => {
  const result = readLocalXianyuChatList(
    connected('account-a'),
    getLocalXianyuChatPage('account-b'),
    { readAt: NOW },
  );

  assert.equal(result.result, 'FAILED');
  if (result.result !== 'FAILED') return;
  assert.equal(result.error_code, 'IDENTITY_UNCONFIRMED');
  assert.equal(result.source_page_version, 'local-fixed-page-v1');
});

void test('expired connection cannot read and repeated valid reads are reproducible', () => {
  const page = getLocalXianyuChatPage('account-a');
  const connection = connected();
  const first = readLocalXianyuChatList(connection, page, { readAt: NOW });
  const repeated = readLocalXianyuChatList(connection, page, { readAt: NOW });
  assert.deepEqual(repeated, first);

  const expired = readLocalXianyuChatList(
    markXianyuReauthRequired(connection),
    page,
    { readAt: NOW },
  );
  assert.equal(expired.result, 'FAILED');
  if (expired.result === 'FAILED') {
    assert.equal(expired.error_code, 'SESSION_EXPIRED');
  }
});

void test('invalid read time is represented as a failed attempt', () => {
  const result = readLocalXianyuChatList(
    connected(),
    getLocalXianyuChatPage('account-a'),
    { readAt: 'not-a-date' },
  );

  assert.equal(result.result, 'FAILED');
  if (result.result === 'FAILED')
    assert.equal(result.error_code, 'READ_TIME_INVALID');
});

void test('stored success is strict, local, and rejects injected fields', () => {
  const sessionStorage = installMemorySessionStorage();
  const accountA = connected('account-a');
  const result = readLocalXianyuChatList(
    accountA,
    getLocalXianyuChatPage('account-a'),
    { readAt: NOW },
  );
  assert.equal(result.result, 'SUCCESS');
  if (result.result !== 'SUCCESS') return;

  let notifications = 0;
  const unsubscribe = subscribeLocalXianyuChatList(() => {
    notifications += 1;
  });
  writeLocalXianyuChatList(result);
  assert.deepEqual(readStoredLocalXianyuChatList(), result);
  assert.equal(notifications, 1);

  const failedRead = readLocalXianyuChatList(
    accountA,
    {
      ...getLocalXianyuChatPage('account-a'),
      source_page_version: 'local-fixed-page-v2',
    } as unknown,
    { readAt: NOW },
  );
  assert.equal(failedRead.result, 'FAILED');
  assert.deepEqual(readStoredLocalXianyuChatList(), result);

  sessionStorage.setItem(
    XIANYU_CHAT_LIST_STORAGE_KEY,
    JSON.stringify({ ...result, token: 'secret-token' }),
  );
  assert.equal(readStoredLocalXianyuChatList(), null);
  assert.equal(sessionStorage.getItem(XIANYU_CHAT_LIST_STORAGE_KEY), null);

  unsubscribe();
});

void test('stored list is bound to its connection and clear removes the local cache', () => {
  const sessionStorage = installMemorySessionStorage();
  const accountA = connected('account-a');
  const accountB = connected('account-b');
  const resultA = readLocalXianyuChatList(
    accountA,
    getLocalXianyuChatPage('account-a'),
    { readAt: NOW },
  );
  const resultB = readLocalXianyuChatList(
    accountB,
    getLocalXianyuChatPage('account-b'),
    { readAt: NOW },
  );
  assert.equal(resultA.result, 'SUCCESS');
  assert.equal(resultB.result, 'SUCCESS');
  if (resultA.result !== 'SUCCESS' || resultB.result !== 'SUCCESS') return;

  writeLocalXianyuChatList(resultA);
  const stored = readStoredLocalXianyuChatList();
  assert.equal(stored?.connection_id, accountA.connection_id);
  assert.equal(stored?.conversations[0]?.conversation_id, 'a-conv-1001');
  assert.notEqual(resultA.connection_id, resultB.connection_id);
  assert.notEqual(
    resultA.conversations[0]?.conversation_id,
    resultB.conversations[0]?.conversation_id,
  );

  clearLocalXianyuChatList();
  assert.equal(sessionStorage.getItem(XIANYU_CHAT_LIST_STORAGE_KEY), null);
  assert.equal(readStoredLocalXianyuChatList(), null);
});

void test('snapshot parser rejects over-limit and malformed stored data', () => {
  const connection = connected();
  const result = readLocalXianyuChatList(
    connection,
    getLocalXianyuChatPage('account-a'),
    { readAt: NOW },
  );
  assert.equal(result.result, 'SUCCESS');
  if (result.result !== 'SUCCESS') return;

  const overLimit = JSON.stringify({
    ...result,
    missing_field_ratio: XIANYU_CHAT_LIST_MISSING_FIELD_LIMIT + 0.01,
  });
  assert.equal(parseLocalXianyuChatListSnapshot(overLimit), null);

  const malformed = JSON.stringify({
    ...result,
    conversations: result.conversations.map((conversation) => ({
      ...conversation,
      unread_count: -1,
    })),
  });
  assert.equal(parseLocalXianyuChatListSnapshot(malformed), null);
});
