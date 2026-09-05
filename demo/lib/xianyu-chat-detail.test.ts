import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  XIANYU_CHAT_DETAIL_MAX_MESSAGES,
  XIANYU_CHAT_DETAIL_STORAGE_KEY,
  clearLocalXianyuChatDetail,
  getLocalXianyuChatDetailPage,
  parseLocalXianyuChatDetailSnapshot,
  readLocalXianyuChatDetail,
  readStoredLocalXianyuChatDetail,
  subscribeLocalXianyuChatDetail,
  writeLocalXianyuChatDetail,
  type XianyuChatDetailReadSuccess,
  type XianyuLocalChatDetailPage,
  type XianyuLocalChatDetailPageMessage,
} from './xianyu-chat-detail.ts';
import {
  createLocalXianyuConnection,
  markXianyuReauthRequired,
  type XianyuFixtureId,
  type XianyuLocalConnection,
} from './xianyu-local-session.ts';
import {
  getLocalXianyuChatPage,
  readLocalXianyuChatList,
  type XianyuChatListReadSuccess,
} from './xianyu-chat-list.ts';

const NOW = '2026-09-05T10:00:00.000Z';

function connected(fixtureId: XianyuFixtureId = 'account-a') {
  return createLocalXianyuConnection(fixtureId, { now: NOW });
}

function confirmedList(
  connection: ReturnType<typeof connected>,
  fixtureId: XianyuFixtureId,
): XianyuChatListReadSuccess {
  const result = readLocalXianyuChatList(
    connection,
    getLocalXianyuChatPage(fixtureId),
    { readAt: NOW },
  );
  assert.equal(result.result, 'SUCCESS');
  if (result.result !== 'SUCCESS') throw new Error('测试夹具列表读取失败');
  return result;
}

function pageWith(
  fixtureId: XianyuFixtureId,
  conversationId: string,
  messages: readonly XianyuLocalChatDetailPageMessage[],
  overrides: Record<string, unknown> = {},
): XianyuLocalChatDetailPage {
  const page = getLocalXianyuChatDetailPage(fixtureId, conversationId);
  if (!page) throw new Error('测试夹具会话不存在');
  return { ...page, ...overrides, messages } as XianyuLocalChatDetailPage;
}

function textMessage(
  messageId: string,
  sentAt: string | null = '2026-09-05T09:00:00.000Z',
): XianyuLocalChatDetailPageMessage {
  return {
    message_id: messageId,
    sender: 'OTHER',
    message_type: 'TEXT',
    sent_at: sentAt,
    text: `测试消息 ${messageId}`,
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

void test('normal detail maps text/system messages and excludes raw credentials', () => {
  const connection = connected();
  const page = getLocalXianyuChatDetailPage('account-a', 'a-conv-1001');
  assert.ok(page);
  const pageWithIgnoredFields = {
    ...page,
    messages: page.messages.map((message) => ({
      ...message,
      token: 'secret-token',
      cookie: 'secret-cookie',
    })),
  };
  const result = readLocalXianyuChatDetail(
    connection,
    confirmedList(connection, 'account-a'),
    'a-conv-1001',
    pageWithIgnoredFields,
    { readAt: NOW },
  );

  assert.equal(result.result, 'SUCCESS');
  if (result.result !== 'SUCCESS') return;
  assert.equal(result.connection_id, connection.connection_id);
  assert.equal(result.conversation_id, 'a-conv-1001');
  assert.equal(result.truncated, false);
  assert.deepEqual(
    result.messages.map((message) => message.message_type),
    [
      'TEXT',
      'SYSTEM',
      'TEXT',
      'IMAGE',
      'PRODUCT_CARD',
      'ORDER_CARD',
      'UNSUPPORTED',
    ],
  );
  assert.equal(result.messages[0]?.sender, 'SELF');
  assert.equal(result.messages[1]?.sender, 'SYSTEM');
  assert.equal(result.messages[0]?.text, '可以，按商品页面说明处理即可。');
  assert.equal(result.messages[3]?.text, null);
  assert.doesNotMatch(
    JSON.stringify(result),
    /手机号|验证码|cookie|token|secret/i,
  );
});

void test('unsupported image, product, order, and unknown types remain visible as controlled placeholders', () => {
  const connection = connected();
  const result = readLocalXianyuChatDetail(
    connection,
    confirmedList(connection, 'account-a'),
    'a-conv-1001',
    pageWith('account-a', 'a-conv-1001', [
      {
        ...textMessage('image'),
        message_type: 'IMAGE',
        text: 'must not be retained',
      },
      {
        ...textMessage('product'),
        message_type: 'PRODUCT_CARD',
      },
      {
        ...textMessage('order'),
        message_type: 'ORDER_CARD',
      },
      {
        ...textMessage('unknown'),
        message_type: 'VIDEO_STICKER',
      },
    ]),
    { readAt: NOW },
  );

  assert.equal(result.result, 'SUCCESS');
  if (result.result !== 'SUCCESS') return;
  assert.deepEqual(
    result.messages
      .map((message) => message.placeholder)
      .sort((left, right) => String(left).localeCompare(String(right))),
    [
      '暂不支持的消息类型：图片消息',
      '暂不支持的消息类型：商品卡片',
      '暂不支持的消息类型：订单卡片',
      '暂不支持的消息类型',
    ].sort((left, right) => left.localeCompare(right)),
  );
  assert.ok(result.messages.every((message) => message.text === null));
});

void test('out-of-order messages sort chronologically and identical duplicates collapse', () => {
  const connection = connected();
  const older = textMessage('older', '2026-09-05T08:00:00.000Z');
  const newer = textMessage('newer', '2026-09-05T09:00:00.000Z');
  const result = readLocalXianyuChatDetail(
    connection,
    confirmedList(connection, 'account-a'),
    'a-conv-1001',
    pageWith('account-a', 'a-conv-1001', [newer, older, { ...newer }]),
    { readAt: NOW },
  );

  assert.equal(result.result, 'SUCCESS');
  if (result.result !== 'SUCCESS') return;
  assert.deepEqual(
    result.messages.map((message) => message.message_id),
    ['older', 'newer'],
  );
});

void test('conflicting duplicate IDs fail closed instead of choosing a message', () => {
  const connection = connected();
  const result = readLocalXianyuChatDetail(
    connection,
    confirmedList(connection, 'account-a'),
    'a-conv-1001',
    pageWith('account-a', 'a-conv-1001', [
      textMessage('same'),
      { ...textMessage('same'), text: '不同内容' },
    ]),
    { readAt: NOW },
  );

  assert.equal(result.result, 'FAILED');
  if (result.result === 'FAILED') {
    assert.equal(result.error_code, 'MESSAGE_CONFLICT');
    assert.equal('messages' in result, false);
  }
});

void test('history is explicitly truncated at the documented maximum', () => {
  const connection = connected();
  const messages = Array.from({ length: 55 }, (_, index) =>
    textMessage(
      `bulk-${String(index).padStart(2, '0')}`,
      `2026-09-05T08:${String(index % 60).padStart(2, '0')}:00.000Z`,
    ),
  );
  const result = readLocalXianyuChatDetail(
    connection,
    confirmedList(connection, 'account-a'),
    'a-conv-1001',
    pageWith('account-a', 'a-conv-1001', messages, { has_more: true }),
    { readAt: NOW },
  );

  assert.equal(result.result, 'SUCCESS');
  if (result.result !== 'SUCCESS') return;
  assert.equal(result.messages.length, XIANYU_CHAT_DETAIL_MAX_MESSAGES);
  assert.equal(result.truncated, true);
  assert.equal(result.messages[0]?.message_id, 'bulk-00');
  assert.equal(result.messages.at(-1)?.message_id, 'bulk-49');
});

void test('empty history succeeds without inventing messages', () => {
  const connection = connected();
  const result = readLocalXianyuChatDetail(
    connection,
    confirmedList(connection, 'account-a'),
    'a-conv-1001',
    pageWith('account-a', 'a-conv-1001', []),
    { readAt: NOW },
  );

  assert.deepEqual(result, {
    schema_version: 1,
    result: 'SUCCESS',
    connection_id: result.connection_id,
    conversation_id: 'a-conv-1001',
    source_page_version: 'local-fixed-page-v1',
    read_at: NOW,
    truncated: false,
    messages: [],
  });
});

void test('mid-read connection expiry prevents committing the detail result', () => {
  const connection = connected();
  let checks = 0;
  const result = readLocalXianyuChatDetail(
    connection,
    confirmedList(connection, 'account-a'),
    'a-conv-1001',
    getLocalXianyuChatDetailPage('account-a', 'a-conv-1001'),
    {
      readAt: NOW,
      isConnectionStillValid: () => {
        checks += 1;
        return checks === 1;
      },
    },
  );

  assert.equal(result.result, 'FAILED');
  if (result.result === 'FAILED') {
    assert.equal(result.error_code, 'SESSION_EXPIRED');
    assert.equal(
      result.error_message,
      '读取期间闲鱼连接已失效，未保存本次结果。',
    );
  }
  assert.equal(checks, 2);
});

void test('expired connections, changed pages, and forged session IDs fail closed', () => {
  const connection = connected();
  const list = confirmedList(connection, 'account-a');
  const page = getLocalXianyuChatDetailPage('account-a', 'a-conv-1001');

  const expired = readLocalXianyuChatDetail(
    markXianyuReauthRequired(connection),
    list,
    'a-conv-1001',
    page,
    { readAt: NOW },
  );
  assert.equal(expired.result, 'FAILED');
  if (expired.result === 'FAILED')
    assert.equal(expired.error_code, 'SESSION_EXPIRED');

  const changedPage = readLocalXianyuChatDetail(
    connection,
    list,
    'a-conv-1001',
    page ? { ...page, source_page_version: 'secret-token-page-v2' } : null,
    { readAt: NOW },
  );
  assert.equal(changedPage.result, 'FAILED');
  if (changedPage.result === 'FAILED') {
    assert.equal(changedPage.error_code, 'PAGE_CHANGED');
    assert.equal(changedPage.source_page_version, 'UNKNOWN');
    assert.doesNotMatch(JSON.stringify(changedPage), /secret-token/i);
  }

  const forgedSession = readLocalXianyuChatDetail(
    connection,
    list,
    'not-in-confirmed-list',
    page,
    { readAt: NOW },
  );
  assert.equal(forgedSession.result, 'FAILED');
  if (forgedSession.result === 'FAILED')
    assert.equal(forgedSession.error_code, 'CONVERSATION_NOT_CONFIRMED');
});

void test('old connection replay and cross-account detail pages are rejected', () => {
  const accountA = connected('account-a');
  const accountB = connected('account-b');
  const listA = confirmedList(accountA, 'account-a');
  const pageA = getLocalXianyuChatDetailPage('account-a', 'a-conv-1001');
  const pageB = getLocalXianyuChatDetailPage('account-b', 'b-conv-2001');

  const oldConnectionReplay = readLocalXianyuChatDetail(
    accountB,
    listA,
    'a-conv-1001',
    pageA,
    { readAt: NOW },
  );
  assert.equal(oldConnectionReplay.result, 'FAILED');
  if (oldConnectionReplay.result === 'FAILED')
    assert.equal(oldConnectionReplay.error_code, 'CONNECTION_MISMATCH');

  const crossAccountPage = readLocalXianyuChatDetail(
    accountA,
    listA,
    'a-conv-1001',
    pageB,
    { readAt: NOW },
  );
  assert.equal(crossAccountPage.result, 'FAILED');
  if (crossAccountPage.result === 'FAILED')
    assert.equal(crossAccountPage.error_code, 'IDENTITY_UNCONFIRMED');
});

void test('forged connection metadata and malformed confirmed lists fail closed', () => {
  const connection = connected();
  const list = confirmedList(connection, 'account-a');
  const page = getLocalXianyuChatDetailPage('account-a', 'a-conv-1001');

  const forgedConnection = {
    ...connection,
    source_page_version: 'local-fixed-page-v2',
  } as unknown as XianyuLocalConnection;
  const forgedConnectionResult = readLocalXianyuChatDetail(
    forgedConnection,
    list,
    'a-conv-1001',
    page,
    { readAt: NOW },
  );
  assert.equal(forgedConnectionResult.result, 'FAILED');
  if (forgedConnectionResult.result === 'FAILED') {
    assert.equal(forgedConnectionResult.error_code, 'IDENTITY_UNCONFIRMED');
  }

  const malformedList = {
    ...list,
    unexpected: 'not-confirmed-data',
  };
  const malformedListResult = readLocalXianyuChatDetail(
    connection,
    malformedList,
    'a-conv-1001',
    page,
    { readAt: NOW },
  );
  assert.equal(malformedListResult.result, 'FAILED');
  if (malformedListResult.result === 'FAILED') {
    assert.equal(malformedListResult.error_code, 'PAGE_CHANGED');
  }
});

void test('stored detail is strict, connection-bound by output, and failed writes preserve success', () => {
  const sessionStorage = installMemorySessionStorage();
  const connection = connected();
  const result = readLocalXianyuChatDetail(
    connection,
    confirmedList(connection, 'account-a'),
    'a-conv-1001',
    getLocalXianyuChatDetailPage('account-a', 'a-conv-1001'),
    { readAt: NOW },
  );
  assert.equal(result.result, 'SUCCESS');
  if (result.result !== 'SUCCESS') return;

  let notifications = 0;
  const unsubscribe = subscribeLocalXianyuChatDetail(() => {
    notifications += 1;
  });
  writeLocalXianyuChatDetail(result);
  assert.deepEqual(readStoredLocalXianyuChatDetail(), result);
  assert.equal(notifications, 1);

  const injected = JSON.stringify({ ...result, token: 'secret-token' });
  sessionStorage.setItem(XIANYU_CHAT_DETAIL_STORAGE_KEY, injected);
  assert.equal(readStoredLocalXianyuChatDetail(), null);
  assert.equal(sessionStorage.getItem(XIANYU_CHAT_DETAIL_STORAGE_KEY), null);
  assert.equal(parseLocalXianyuChatDetailSnapshot(injected), null);

  assert.throws(
    () =>
      writeLocalXianyuChatDetail({
        ...result,
        token: 'secret-token',
      } as XianyuChatDetailReadSuccess & { token: string }),
    /白名单结构/,
  );
  assert.equal(sessionStorage.getItem(XIANYU_CHAT_DETAIL_STORAGE_KEY), null);

  unsubscribe();
});

void test('clear removes detail cache and notifications remain local to the current tab', () => {
  const sessionStorage = installMemorySessionStorage();
  const connection = connected();
  const result = readLocalXianyuChatDetail(
    connection,
    confirmedList(connection, 'account-a'),
    'a-conv-1001',
    getLocalXianyuChatDetailPage('account-a', 'a-conv-1001'),
    { readAt: NOW },
  );
  assert.equal(result.result, 'SUCCESS');
  if (result.result !== 'SUCCESS') return;
  writeLocalXianyuChatDetail(result);
  assert.ok(sessionStorage.getItem(XIANYU_CHAT_DETAIL_STORAGE_KEY));
  clearLocalXianyuChatDetail();
  assert.equal(sessionStorage.getItem(XIANYU_CHAT_DETAIL_STORAGE_KEY), null);
  assert.equal(readStoredLocalXianyuChatDetail(), null);
});
