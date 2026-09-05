import {
  XIANYU_LOCAL_FIXTURES,
  XIANYU_LOCAL_PAGE_VERSION,
  parseLocalXianyuConnection,
  type XianyuFixtureId,
  type XianyuLocalConnection,
} from './xianyu-local-session.ts';
import { parseLocalXianyuChatListSnapshot } from './xianyu-chat-list.ts';

export const XIANYU_CHAT_DETAIL_SCHEMA_VERSION = 1;
export const XIANYU_CHAT_DETAIL_STORAGE_KEY =
  'harbor-support-xianyu-local-chat-detail';
export const XIANYU_CHAT_DETAIL_MAX_MESSAGES = 50;

const DETAIL_FIELDS = [
  'schema_version',
  'result',
  'connection_id',
  'conversation_id',
  'source_page_version',
  'read_at',
  'truncated',
  'messages',
] as const;
const MESSAGE_FIELDS = [
  'message_id',
  'sender',
  'message_type',
  'sent_at',
  'text',
  'placeholder',
] as const;

export type XianyuLocalChatDetailPageMessage = {
  message_id: string;
  sender: string;
  message_type: string;
  sent_at: string | null;
  text: string | null;
};

export type XianyuLocalChatDetailPage = {
  source_page: 'LOCAL_FIXED_PAGE';
  source_page_version: typeof XIANYU_LOCAL_PAGE_VERSION;
  fixture_id: XianyuFixtureId;
  conversation_id: string;
  has_more: boolean;
  messages: readonly XianyuLocalChatDetailPageMessage[];
};

export type XianyuChatMessageSender = 'SELF' | 'OTHER' | 'SYSTEM' | 'UNKNOWN';
export type XianyuChatMessageType =
  | 'TEXT'
  | 'SYSTEM'
  | 'IMAGE'
  | 'PRODUCT_CARD'
  | 'ORDER_CARD'
  | 'UNSUPPORTED';

export type XianyuChatDetailMessage = {
  message_id: string;
  sender: XianyuChatMessageSender;
  message_type: XianyuChatMessageType;
  sent_at: string | null;
  text: string | null;
  placeholder: string | null;
};

export type XianyuChatDetailReadSuccess = {
  schema_version: typeof XIANYU_CHAT_DETAIL_SCHEMA_VERSION;
  result: 'SUCCESS';
  connection_id: string;
  conversation_id: string;
  source_page_version: string;
  read_at: string;
  truncated: boolean;
  messages: readonly XianyuChatDetailMessage[];
};

export type XianyuChatDetailReadFailure = {
  schema_version: typeof XIANYU_CHAT_DETAIL_SCHEMA_VERSION;
  result: 'FAILED';
  connection_id: string;
  conversation_id: string;
  source_page_version: string;
  read_at: string;
  error_code:
    | 'SESSION_EXPIRED'
    | 'CONNECTION_MISMATCH'
    | 'CONVERSATION_NOT_CONFIRMED'
    | 'PAGE_CHANGED'
    | 'IDENTITY_UNCONFIRMED'
    | 'MESSAGE_CONFLICT'
    | 'READ_TIME_INVALID';
  error_message: string;
};

export type XianyuChatDetailRead =
  | XianyuChatDetailReadSuccess
  | XianyuChatDetailReadFailure;

export type XianyuChatDetailReadOptions = {
  readAt?: string;
  isConnectionStillValid?: () => boolean;
};

const unsupportedPlaceholders: Record<
  Exclude<XianyuChatMessageType, 'TEXT' | 'SYSTEM'>,
  string
> = {
  IMAGE: '暂不支持的消息类型：图片消息',
  PRODUCT_CARD: '暂不支持的消息类型：商品卡片',
  ORDER_CARD: '暂不支持的消息类型：订单卡片',
  UNSUPPORTED: '暂不支持的消息类型',
};

function textMessage(
  messageId: string,
  sender: 'SELF' | 'OTHER',
  text: string,
  sentAt: string,
): XianyuLocalChatDetailPageMessage {
  return {
    message_id: messageId,
    sender,
    message_type: 'TEXT',
    sent_at: sentAt,
    text,
  };
}

function systemMessage(
  messageId: string,
  text: string,
  sentAt: string,
): XianyuLocalChatDetailPageMessage {
  return {
    message_id: messageId,
    sender: 'SYSTEM',
    message_type: 'SYSTEM',
    sent_at: sentAt,
    text,
  };
}

function unsupportedMessage(
  messageId: string,
  sender: 'SELF' | 'OTHER' | 'SYSTEM',
  messageType: string,
  sentAt: string,
): XianyuLocalChatDetailPageMessage {
  return {
    message_id: messageId,
    sender,
    message_type: messageType,
    sent_at: sentAt,
    text: null,
  };
}

const localChatDetailPages: Readonly<
  Record<XianyuFixtureId, Readonly<Record<string, XianyuLocalChatDetailPage>>>
> = {
  'account-a': {
    'a-conv-1001': {
      source_page: 'LOCAL_FIXED_PAGE',
      source_page_version: XIANYU_LOCAL_PAGE_VERSION,
      fixture_id: 'account-a',
      conversation_id: 'a-conv-1001',
      has_more: false,
      messages: [
        textMessage(
          'a-msg-1001',
          'SELF',
          '可以，按商品页面说明处理即可。',
          '2026-09-05T09:50:00.000Z',
        ),
        systemMessage(
          'a-msg-1002',
          '订单已发货，物流信息由平台展示。',
          '2026-09-05T09:52:00.000Z',
        ),
        textMessage(
          'a-msg-1003',
          'OTHER',
          '尺码可以换吗？',
          '2026-09-05T09:58:00.000Z',
        ),
        unsupportedMessage(
          'a-msg-1004',
          'OTHER',
          'IMAGE',
          '2026-09-05T09:59:00.000Z',
        ),
        unsupportedMessage(
          'a-msg-1005',
          'OTHER',
          'PRODUCT_CARD',
          '2026-09-05T10:00:00.000Z',
        ),
        unsupportedMessage(
          'a-msg-1006',
          'SYSTEM',
          'ORDER_CARD',
          '2026-09-05T10:01:00.000Z',
        ),
        unsupportedMessage(
          'a-msg-1007',
          'OTHER',
          'STICKER',
          '2026-09-05T10:02:00.000Z',
        ),
      ],
    },
    'a-conv-1002': {
      source_page: 'LOCAL_FIXED_PAGE',
      source_page_version: XIANYU_LOCAL_PAGE_VERSION,
      fixture_id: 'account-a',
      conversation_id: 'a-conv-1002',
      has_more: false,
      messages: [
        textMessage(
          'a-msg-2001',
          'OTHER',
          '收到啦，谢谢。',
          '2026-09-05T09:42:00.000Z',
        ),
      ],
    },
    'a-conv-1003': {
      source_page: 'LOCAL_FIXED_PAGE',
      source_page_version: XIANYU_LOCAL_PAGE_VERSION,
      fixture_id: 'account-a',
      conversation_id: 'a-conv-1003',
      has_more: false,
      messages: [
        systemMessage(
          'a-msg-3001',
          '会话由平台系统创建。',
          '2026-09-05T09:15:00.000Z',
        ),
      ],
    },
    'a-conv-1004': {
      source_page: 'LOCAL_FIXED_PAGE',
      source_page_version: XIANYU_LOCAL_PAGE_VERSION,
      fixture_id: 'account-a',
      conversation_id: 'a-conv-1004',
      has_more: false,
      messages: [
        textMessage(
          'a-msg-4001',
          'OTHER',
          '已发出，单号稍后更新。',
          '2026-09-05T08:30:00.000Z',
        ),
      ],
    },
    'a-conv-1005': {
      source_page: 'LOCAL_FIXED_PAGE',
      source_page_version: XIANYU_LOCAL_PAGE_VERSION,
      fixture_id: 'account-a',
      conversation_id: 'a-conv-1005',
      has_more: false,
      messages: [
        textMessage(
          'a-msg-5001',
          'OTHER',
          '好的。',
          '2026-09-05T07:50:00.000Z',
        ),
      ],
    },
  },
  'account-b': {
    'b-conv-2001': {
      source_page: 'LOCAL_FIXED_PAGE',
      source_page_version: XIANYU_LOCAL_PAGE_VERSION,
      fixture_id: 'account-b',
      conversation_id: 'b-conv-2001',
      has_more: false,
      messages: [
        textMessage(
          'b-msg-2001',
          'OTHER',
          '想确认发货时间。',
          '2026-09-05T09:54:00.000Z',
        ),
        systemMessage(
          'b-msg-2002',
          '当前消息来自本地模拟系统。',
          '2026-09-05T09:55:00.000Z',
        ),
        unsupportedMessage(
          'b-msg-2003',
          'OTHER',
          'ORDER_CARD',
          '2026-09-05T09:56:00.000Z',
        ),
      ],
    },
    'b-conv-2002': {
      source_page: 'LOCAL_FIXED_PAGE',
      source_page_version: XIANYU_LOCAL_PAGE_VERSION,
      fixture_id: 'account-b',
      conversation_id: 'b-conv-2002',
      has_more: false,
      messages: [
        textMessage(
          'b-msg-2101',
          'OTHER',
          '请问还在吗？',
          '2026-09-05T09:36:00.000Z',
        ),
      ],
    },
    'b-conv-2003': {
      source_page: 'LOCAL_FIXED_PAGE',
      source_page_version: XIANYU_LOCAL_PAGE_VERSION,
      fixture_id: 'account-b',
      conversation_id: 'b-conv-2003',
      has_more: false,
      messages: [
        systemMessage(
          'b-msg-2201',
          '该会话暂无可识别的文本消息。',
          '2026-09-05T09:00:00.000Z',
        ),
      ],
    },
  },
};

export function getLocalXianyuChatDetailPage(
  fixtureId: XianyuFixtureId,
  conversationId: string,
): XianyuLocalChatDetailPage | null {
  const page = localChatDetailPages[fixtureId][conversationId];
  if (!page) return null;
  return {
    ...page,
    messages: page.messages.map((message) => ({ ...message })),
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function hasExactFields(
  value: Record<string, unknown>,
  fields: readonly string[],
): boolean {
  const keys = Object.keys(value);
  return (
    keys.length === fields.length &&
    fields.every((field) => Object.hasOwn(value, field))
  );
}

function isIsoDate(value: unknown): value is string {
  return typeof value === 'string' && Number.isFinite(Date.parse(value));
}

function fixtureIdForConnection(
  connection: XianyuLocalConnection,
): XianyuFixtureId | null {
  return (
    XIANYU_LOCAL_FIXTURES.find(
      (fixture) => fixture.display_identifier === connection.display_identifier,
    )?.id ?? null
  );
}

function serializeRecord(value: unknown): string | null {
  try {
    const raw = JSON.stringify(value);
    return typeof raw === 'string' ? raw : null;
  } catch {
    return null;
  }
}

function trustedConnectedConnection(
  connection: XianyuLocalConnection,
): XianyuLocalConnection | null {
  const raw = serializeRecord(connection);
  if (!raw) return null;
  const parsed = parseLocalXianyuConnection(raw);
  return parsed?.status === 'CONNECTED' ? parsed : null;
}

function optionalText(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function optionalDate(value: unknown): string | null {
  return isIsoDate(value) ? value : null;
}

function messageType(value: unknown): XianyuChatMessageType {
  if (
    value === 'TEXT' ||
    value === 'SYSTEM' ||
    value === 'IMAGE' ||
    value === 'PRODUCT_CARD' ||
    value === 'ORDER_CARD'
  ) {
    return value;
  }
  return 'UNSUPPORTED';
}

function messageSender(value: unknown): XianyuChatMessageSender {
  if (value === 'SELF' || value === 'OTHER' || value === 'SYSTEM') {
    return value;
  }
  return 'UNKNOWN';
}

function normalizeMessage(
  value: Record<string, unknown>,
): XianyuChatDetailMessage | null {
  if (typeof value.message_id !== 'string' || !value.message_id.trim()) {
    return null;
  }
  const type = messageType(value.message_type);
  const isTextual = type === 'TEXT' || type === 'SYSTEM';
  return {
    message_id: value.message_id.trim(),
    sender: messageSender(value.sender),
    message_type: type,
    sent_at: optionalDate(value.sent_at),
    text: isTextual ? optionalText(value.text) : null,
    placeholder: isTextual ? null : unsupportedPlaceholders[type],
  };
}

function observedPageVersion(page: unknown): string {
  if (
    isRecord(page) &&
    page.source_page_version === XIANYU_LOCAL_PAGE_VERSION
  ) {
    return page.source_page_version;
  }
  return 'UNKNOWN';
}

function readTimestamp(options: XianyuChatDetailReadOptions): {
  value: string;
  invalid: boolean;
} {
  const value = options.readAt ?? new Date().toISOString();
  return { value, invalid: !isIsoDate(value) };
}

function failed(
  connection: XianyuLocalConnection,
  conversationId: string,
  page: unknown,
  readAt: string,
  errorCode: XianyuChatDetailReadFailure['error_code'],
  errorMessage: string,
): XianyuChatDetailReadFailure {
  return {
    schema_version: XIANYU_CHAT_DETAIL_SCHEMA_VERSION,
    result: 'FAILED',
    connection_id: connection.connection_id,
    conversation_id: conversationId,
    source_page_version: observedPageVersion(page),
    read_at: readAt,
    error_code: errorCode,
    error_message: errorMessage,
  };
}

function confirmedConversation(
  chatList: unknown,
  connection: XianyuLocalConnection,
  conversationId: string,
): 'CONFIRMED' | 'CONNECTION_MISMATCH' | 'NOT_CONFIRMED' | 'MALFORMED' {
  if (!isRecord(chatList)) return 'MALFORMED';
  if (chatList.result !== 'SUCCESS') return 'NOT_CONFIRMED';
  if (chatList.connection_id !== connection.connection_id) {
    return 'CONNECTION_MISMATCH';
  }
  const raw = serializeRecord(chatList);
  if (!raw) return 'MALFORMED';
  const parsed = parseLocalXianyuChatListSnapshot(raw);
  if (!parsed) return 'MALFORMED';
  return parsed.conversations.some(
    (conversation) => conversation.conversation_id === conversationId,
  )
    ? 'CONFIRMED'
    : 'NOT_CONFIRMED';
}

function sortMessages(
  messages: readonly XianyuChatDetailMessage[],
): XianyuChatDetailMessage[] {
  return [...messages].sort((left, right) => {
    const leftTime = left.sent_at
      ? Date.parse(left.sent_at)
      : Number.POSITIVE_INFINITY;
    const rightTime = right.sent_at
      ? Date.parse(right.sent_at)
      : Number.POSITIVE_INFINITY;
    if (leftTime !== rightTime) return leftTime - rightTime;
    if (left.message_id === right.message_id) return 0;
    return left.message_id < right.message_id ? -1 : 1;
  });
}

function sameMessage(
  left: XianyuChatDetailMessage,
  right: XianyuChatDetailMessage,
): boolean {
  return (
    left.message_id === right.message_id &&
    left.sender === right.sender &&
    left.message_type === right.message_type &&
    left.sent_at === right.sent_at &&
    left.text === right.text &&
    left.placeholder === right.placeholder
  );
}

export function readLocalXianyuChatDetail(
  connection: XianyuLocalConnection,
  chatList: unknown,
  conversationId: string,
  page: unknown,
  options: XianyuChatDetailReadOptions = {},
): XianyuChatDetailRead {
  const timestamp = readTimestamp(options);
  if (timestamp.invalid) {
    return failed(
      connection,
      conversationId,
      page,
      new Date().toISOString(),
      'READ_TIME_INVALID',
      '读取时间无效，未保存本次结果。',
    );
  }
  if (connection.status !== 'CONNECTED') {
    return failed(
      connection,
      conversationId,
      page,
      timestamp.value,
      'SESSION_EXPIRED',
      '当前闲鱼连接已失效，请重新登录后再读取。',
    );
  }
  if (!trustedConnectedConnection(connection)) {
    return failed(
      connection,
      conversationId,
      page,
      timestamp.value,
      'IDENTITY_UNCONFIRMED',
      '无法确认当前连接身份，未读取会话详情。',
    );
  }
  if (options.isConnectionStillValid && !options.isConnectionStillValid()) {
    return failed(
      connection,
      conversationId,
      page,
      timestamp.value,
      'SESSION_EXPIRED',
      '读取期间闲鱼连接已失效，未保存本次结果。',
    );
  }
  if (!conversationId.trim()) {
    return failed(
      connection,
      conversationId,
      page,
      timestamp.value,
      'CONVERSATION_NOT_CONFIRMED',
      '当前会话未被已确认的聊天列表证明，未读取消息。',
    );
  }

  const confirmation = confirmedConversation(
    chatList,
    connection,
    conversationId,
  );
  if (confirmation === 'CONNECTION_MISMATCH') {
    return failed(
      connection,
      conversationId,
      page,
      timestamp.value,
      'CONNECTION_MISMATCH',
      '聊天列表属于其他本地连接，未读取会话详情。',
    );
  }
  if (confirmation === 'MALFORMED') {
    return failed(
      connection,
      conversationId,
      page,
      timestamp.value,
      'PAGE_CHANGED',
      '聊天列表页面已变化，需要重新适配。',
    );
  }
  if (confirmation === 'NOT_CONFIRMED') {
    return failed(
      connection,
      conversationId,
      page,
      timestamp.value,
      'CONVERSATION_NOT_CONFIRMED',
      '当前会话未被已确认的聊天列表证明，未读取消息。',
    );
  }

  if (!isRecord(page)) {
    return failed(
      connection,
      conversationId,
      page,
      timestamp.value,
      'PAGE_CHANGED',
      '闲鱼页面已变化，需要重新适配。',
    );
  }
  const expectedFixtureId = fixtureIdForConnection(connection);
  if (!expectedFixtureId) {
    return failed(
      connection,
      conversationId,
      page,
      timestamp.value,
      'IDENTITY_UNCONFIRMED',
      '无法确认当前页面属于已连接账号，未读取会话详情。',
    );
  }
  if (
    page.source_page !== 'LOCAL_FIXED_PAGE' ||
    page.source_page_version !== XIANYU_LOCAL_PAGE_VERSION
  ) {
    return failed(
      connection,
      conversationId,
      page,
      timestamp.value,
      'PAGE_CHANGED',
      '闲鱼页面已变化，需要重新适配。',
    );
  }
  if (page.fixture_id !== expectedFixtureId) {
    return failed(
      connection,
      conversationId,
      page,
      timestamp.value,
      'IDENTITY_UNCONFIRMED',
      '无法确认当前页面属于已连接账号，未读取会话详情。',
    );
  }
  if (page.conversation_id !== conversationId) {
    return failed(
      connection,
      conversationId,
      page,
      timestamp.value,
      'CONVERSATION_NOT_CONFIRMED',
      '当前页面不是已确认的会话，未读取消息。',
    );
  }
  if (!Array.isArray(page.messages) || typeof page.has_more !== 'boolean') {
    return failed(
      connection,
      conversationId,
      page,
      timestamp.value,
      'PAGE_CHANGED',
      '闲鱼页面已变化，需要重新适配。',
    );
  }

  const messagesById = new Map<string, XianyuChatDetailMessage>();
  for (const rawMessage of page.messages) {
    if (!isRecord(rawMessage)) {
      return failed(
        connection,
        conversationId,
        page,
        timestamp.value,
        'PAGE_CHANGED',
        '闲鱼页面已变化，需要重新适配。',
      );
    }
    const message = normalizeMessage(rawMessage);
    if (!message) {
      return failed(
        connection,
        conversationId,
        page,
        timestamp.value,
        'PAGE_CHANGED',
        '闲鱼页面已变化，需要重新适配。',
      );
    }
    const existing = messagesById.get(message.message_id);
    if (existing) {
      if (!sameMessage(existing, message)) {
        return failed(
          connection,
          conversationId,
          page,
          timestamp.value,
          'MESSAGE_CONFLICT',
          '同一消息标识对应的内容不一致，未读取会话详情。',
        );
      }
      continue;
    }
    messagesById.set(message.message_id, message);
  }

  const sorted = sortMessages([...messagesById.values()]);
  if (options.isConnectionStillValid && !options.isConnectionStillValid()) {
    return failed(
      connection,
      conversationId,
      page,
      timestamp.value,
      'SESSION_EXPIRED',
      '读取期间闲鱼连接已失效，未保存本次结果。',
    );
  }
  return {
    schema_version: XIANYU_CHAT_DETAIL_SCHEMA_VERSION,
    result: 'SUCCESS',
    connection_id: connection.connection_id,
    conversation_id: conversationId,
    source_page_version: XIANYU_LOCAL_PAGE_VERSION,
    read_at: timestamp.value,
    truncated:
      page.has_more || page.messages.length > XIANYU_CHAT_DETAIL_MAX_MESSAGES,
    messages: sorted.slice(0, XIANYU_CHAT_DETAIL_MAX_MESSAGES),
  };
}

function parseStoredMessage(value: unknown): XianyuChatDetailMessage | null {
  if (!isRecord(value) || !hasExactFields(value, MESSAGE_FIELDS)) return null;
  const messageType = value.message_type;
  const isKnownType =
    messageType === 'TEXT' ||
    messageType === 'SYSTEM' ||
    messageType === 'IMAGE' ||
    messageType === 'PRODUCT_CARD' ||
    messageType === 'ORDER_CARD' ||
    messageType === 'UNSUPPORTED';
  const isKnownSender =
    value.sender === 'SELF' ||
    value.sender === 'OTHER' ||
    value.sender === 'SYSTEM' ||
    value.sender === 'UNKNOWN';
  if (
    typeof value.message_id !== 'string' ||
    !value.message_id.trim() ||
    !isKnownSender ||
    !isKnownType ||
    (value.sent_at !== null && !isIsoDate(value.sent_at)) ||
    (value.text !== null && typeof value.text !== 'string') ||
    (value.placeholder !== null && typeof value.placeholder !== 'string')
  ) {
    return null;
  }
  const textual = messageType === 'TEXT' || messageType === 'SYSTEM';
  if (
    (textual && value.placeholder !== null) ||
    (!textual &&
      (value.text !== null ||
        value.placeholder !== unsupportedPlaceholders[messageType]))
  ) {
    return null;
  }
  return value as XianyuChatDetailMessage;
}

export function parseLocalXianyuChatDetailSnapshot(
  raw: string | null,
): XianyuChatDetailReadSuccess | null {
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (
      !isRecord(parsed) ||
      !hasExactFields(parsed, DETAIL_FIELDS) ||
      parsed.schema_version !== XIANYU_CHAT_DETAIL_SCHEMA_VERSION ||
      parsed.result !== 'SUCCESS' ||
      typeof parsed.connection_id !== 'string' ||
      !parsed.connection_id ||
      typeof parsed.conversation_id !== 'string' ||
      !parsed.conversation_id ||
      parsed.source_page_version !== XIANYU_LOCAL_PAGE_VERSION ||
      !isIsoDate(parsed.read_at) ||
      typeof parsed.truncated !== 'boolean' ||
      !Array.isArray(parsed.messages) ||
      parsed.messages.length > XIANYU_CHAT_DETAIL_MAX_MESSAGES
    ) {
      return null;
    }
    const messages = parsed.messages.map(parseStoredMessage);
    if (messages.some((message) => message === null)) return null;
    const ids = new Set(messages.map((message) => message?.message_id));
    if (ids.size !== messages.length) return null;
    return {
      ...(parsed as Omit<XianyuChatDetailReadSuccess, 'messages'>),
      messages: messages as XianyuChatDetailMessage[],
    };
  } catch {
    return null;
  }
}

type LocalChatDetailListener = () => void;
const listeners = new Set<LocalChatDetailListener>();
let cachedStorage: Storage | null | undefined;
let cachedRaw: string | null | undefined;
let cachedSnapshot: XianyuChatDetailReadSuccess | null = null;

export function readStoredLocalXianyuChatDetail(): XianyuChatDetailReadSuccess | null {
  if (typeof window === 'undefined') return null;
  const storage = window.sessionStorage;
  if (cachedStorage !== storage) {
    cachedStorage = storage;
    cachedRaw = undefined;
    cachedSnapshot = null;
  }
  const raw = storage.getItem(XIANYU_CHAT_DETAIL_STORAGE_KEY);
  if (raw === cachedRaw) return cachedSnapshot;
  const snapshot = parseLocalXianyuChatDetailSnapshot(raw);
  if (!snapshot && raw !== null) {
    storage.removeItem(XIANYU_CHAT_DETAIL_STORAGE_KEY);
  }
  cachedRaw = snapshot ? raw : null;
  cachedSnapshot = snapshot;
  return snapshot;
}

export function writeLocalXianyuChatDetail(
  snapshot: XianyuChatDetailReadSuccess,
): void {
  const parsed = parseLocalXianyuChatDetailSnapshot(JSON.stringify(snapshot));
  if (!parsed) throw new Error('会话详情结果不符合本地白名单结构');
  const serialized = JSON.stringify(parsed);
  window.sessionStorage.setItem(XIANYU_CHAT_DETAIL_STORAGE_KEY, serialized);
  cachedStorage = window.sessionStorage;
  cachedRaw = serialized;
  cachedSnapshot = parsed;
  listeners.forEach((listener) => listener());
}

export function clearLocalXianyuChatDetail(): void {
  if (typeof window !== 'undefined') {
    window.sessionStorage.removeItem(XIANYU_CHAT_DETAIL_STORAGE_KEY);
    cachedStorage = window.sessionStorage;
    cachedRaw = null;
    cachedSnapshot = null;
    listeners.forEach((listener) => listener());
  }
}

export function subscribeLocalXianyuChatDetail(
  listener: LocalChatDetailListener,
): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
