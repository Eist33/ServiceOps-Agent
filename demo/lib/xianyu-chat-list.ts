import {
  XIANYU_LOCAL_FIXTURES,
  XIANYU_LOCAL_PAGE_VERSION,
  type XianyuFixtureId,
  type XianyuLocalConnection,
} from './xianyu-local-session.ts';

export const XIANYU_CHAT_LIST_SCHEMA_VERSION = 1;
export const XIANYU_CHAT_LIST_STORAGE_KEY =
  'harbor-support-xianyu-local-chat-list';
export const XIANYU_CHAT_LIST_MAX = 20;
export const XIANYU_CHAT_LIST_MISSING_FIELD_LIMIT = 0.25;

const CHAT_LIST_FIELDS = [
  'schema_version',
  'result',
  'connection_id',
  'source_page_version',
  'read_at',
  'truncated',
  'missing_field_ratio',
  'conversations',
] as const;
const CONVERSATION_FIELDS = [
  'conversation_id',
  'avatar_ref',
  'nickname',
  'last_message_summary',
  'last_message_at',
  'unread_count',
  'is_pinned',
  'is_muted',
] as const;
const MAPPED_FIELDS = [
  'avatar_ref',
  'nickname',
  'last_message_summary',
  'last_message_at',
  'unread_count',
  'is_pinned',
  'is_muted',
] as const;

export type XianyuLocalChatPageRow = {
  conversation_id: string;
  avatar_ref: string | null;
  nickname: string | null;
  last_message_summary: string | null;
  last_message_at: string | null;
  unread_count: number | null;
  is_pinned: boolean | null;
  is_muted: boolean | null;
};

export type XianyuLocalChatPage = {
  source_page: 'LOCAL_FIXED_PAGE';
  source_page_version: typeof XIANYU_LOCAL_PAGE_VERSION;
  fixture_id: XianyuFixtureId;
  has_more: boolean;
  conversations: readonly XianyuLocalChatPageRow[];
};

export type XianyuChatConversation = XianyuLocalChatPageRow;

export type XianyuChatListReadSuccess = {
  schema_version: typeof XIANYU_CHAT_LIST_SCHEMA_VERSION;
  result: 'SUCCESS';
  connection_id: string;
  source_page_version: string;
  read_at: string;
  truncated: boolean;
  missing_field_ratio: number;
  conversations: readonly XianyuChatConversation[];
};

export type XianyuChatListReadFailure = {
  schema_version: typeof XIANYU_CHAT_LIST_SCHEMA_VERSION;
  result: 'FAILED';
  connection_id: string;
  source_page_version: string;
  read_at: string;
  error_code:
    | 'SESSION_EXPIRED'
    | 'PAGE_CHANGED'
    | 'IDENTITY_UNCONFIRMED'
    | 'FIELD_COVERAGE_TOO_LOW'
    | 'READ_TIME_INVALID';
  error_message: string;
};

export type XianyuChatListRead =
  | XianyuChatListReadSuccess
  | XianyuChatListReadFailure;

const localChatPages: Readonly<Record<XianyuFixtureId, XianyuLocalChatPage>> = {
  'account-a': {
    source_page: 'LOCAL_FIXED_PAGE',
    source_page_version: XIANYU_LOCAL_PAGE_VERSION,
    fixture_id: 'account-a',
    has_more: false,
    conversations: [
      {
        conversation_id: 'a-conv-1001',
        avatar_ref: 'avatar-a-001',
        nickname: '晨光手作',
        last_message_summary: '尺码可以换吗？',
        last_message_at: '2026-09-05T09:58:00.000Z',
        unread_count: 2,
        is_pinned: true,
        is_muted: false,
      },
      {
        conversation_id: 'a-conv-1002',
        avatar_ref: 'avatar-a-002',
        nickname: '同名买家',
        last_message_summary: '收到啦，谢谢',
        last_message_at: '2026-09-05T09:42:00.000Z',
        unread_count: 0,
        is_pinned: false,
        is_muted: false,
      },
      {
        conversation_id: 'a-conv-1003',
        avatar_ref: null,
        nickname: '城市漫游',
        last_message_summary: null,
        last_message_at: '2026-09-05T09:15:00.000Z',
        unread_count: null,
        is_pinned: false,
        is_muted: true,
      },
      {
        conversation_id: 'a-conv-1004',
        avatar_ref: 'avatar-a-004',
        nickname: '橙子小铺',
        last_message_summary: '已发出，单号稍后更新',
        last_message_at: '2026-09-05T08:30:00.000Z',
        unread_count: 1,
        is_pinned: false,
        is_muted: false,
      },
      {
        conversation_id: 'a-conv-1005',
        avatar_ref: 'avatar-a-005',
        nickname: '静音提醒',
        last_message_summary: '好的',
        last_message_at: '2026-09-05T07:50:00.000Z',
        unread_count: 0,
        is_pinned: false,
        is_muted: true,
      },
    ],
  },
  'account-b': {
    source_page: 'LOCAL_FIXED_PAGE',
    source_page_version: XIANYU_LOCAL_PAGE_VERSION,
    fixture_id: 'account-b',
    has_more: false,
    conversations: [
      {
        conversation_id: 'b-conv-2001',
        avatar_ref: 'avatar-b-001',
        nickname: '同名买家',
        last_message_summary: '想确认发货时间',
        last_message_at: '2026-09-05T09:54:00.000Z',
        unread_count: 4,
        is_pinned: true,
        is_muted: false,
      },
      {
        conversation_id: 'b-conv-2002',
        avatar_ref: 'avatar-b-002',
        nickname: '远山来信',
        last_message_summary: '请问还在吗？',
        last_message_at: '2026-09-05T09:36:00.000Z',
        unread_count: 1,
        is_pinned: false,
        is_muted: false,
      },
      {
        conversation_id: 'b-conv-2003',
        avatar_ref: null,
        nickname: '旧物新知',
        last_message_summary: null,
        last_message_at: null,
        unread_count: 0,
        is_pinned: false,
        is_muted: true,
      },
    ],
  },
};

export function getLocalXianyuChatPage(
  fixtureId: XianyuFixtureId,
): XianyuLocalChatPage {
  const page = localChatPages[fixtureId];
  if (!page) throw new Error('本地固定聊天页面不存在');
  return {
    ...page,
    conversations: page.conversations.map((conversation) => ({
      ...conversation,
    })),
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

function optionalString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function optionalDate(value: unknown): string | null {
  return isIsoDate(value) ? value : null;
}

function optionalUnreadCount(value: unknown): number | null {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0
    ? value
    : null;
}

function optionalBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null;
}

function observedPageVersion(page: unknown): string {
  if (isRecord(page) && typeof page.source_page_version === 'string') {
    return page.source_page_version;
  }
  return 'UNKNOWN';
}

function readTimestamp(options: { readAt?: string }): {
  value: string;
  invalid: boolean;
} {
  const value = options.readAt ?? new Date().toISOString();
  return { value, invalid: !isIsoDate(value) };
}

function failed(
  connection: XianyuLocalConnection,
  page: unknown,
  readAt: string,
  errorCode: XianyuChatListReadFailure['error_code'],
  errorMessage: string,
): XianyuChatListReadFailure {
  return {
    schema_version: XIANYU_CHAT_LIST_SCHEMA_VERSION,
    result: 'FAILED',
    connection_id: connection.connection_id,
    source_page_version: observedPageVersion(page),
    read_at: readAt,
    error_code: errorCode,
    error_message: errorMessage,
  };
}

function sortConversations(
  conversations: readonly XianyuChatConversation[],
): XianyuChatConversation[] {
  return [...conversations].sort((left, right) => {
    const pinnedDelta =
      Number(right.is_pinned === true) - Number(left.is_pinned === true);
    if (pinnedDelta !== 0) return pinnedDelta;

    const leftTime = left.last_message_at
      ? Date.parse(left.last_message_at)
      : Number.NEGATIVE_INFINITY;
    const rightTime = right.last_message_at
      ? Date.parse(right.last_message_at)
      : Number.NEGATIVE_INFINITY;
    if (leftTime !== rightTime) return rightTime - leftTime;
    if (left.conversation_id === right.conversation_id) return 0;
    return left.conversation_id < right.conversation_id ? -1 : 1;
  });
}

export function readLocalXianyuChatList(
  connection: XianyuLocalConnection,
  page: unknown,
  options: { readAt?: string } = {},
): XianyuChatListRead {
  const timestamp = readTimestamp(options);
  if (timestamp.invalid) {
    return failed(
      connection,
      page,
      new Date().toISOString(),
      'READ_TIME_INVALID',
      '读取时间无效，未保存本次结果。',
    );
  }
  if (connection.status !== 'CONNECTED') {
    return failed(
      connection,
      page,
      timestamp.value,
      'SESSION_EXPIRED',
      '当前闲鱼连接已失效，请重新登录后再读取。',
    );
  }

  if (!isRecord(page)) {
    return failed(
      connection,
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
      page,
      timestamp.value,
      'IDENTITY_UNCONFIRMED',
      '无法确认当前页面属于已连接账号，未读取聊天列表。',
    );
  }
  if (
    page.source_page !== 'LOCAL_FIXED_PAGE' ||
    page.source_page_version !== XIANYU_LOCAL_PAGE_VERSION
  ) {
    return failed(
      connection,
      page,
      timestamp.value,
      'PAGE_CHANGED',
      '闲鱼页面已变化，需要重新适配。',
    );
  }
  if (page.fixture_id !== expectedFixtureId) {
    return failed(
      connection,
      page,
      timestamp.value,
      'IDENTITY_UNCONFIRMED',
      '无法确认当前页面属于已连接账号，未读取聊天列表。',
    );
  }
  if (
    !Array.isArray(page.conversations) ||
    typeof page.has_more !== 'boolean'
  ) {
    return failed(
      connection,
      page,
      timestamp.value,
      'PAGE_CHANGED',
      '闲鱼页面已变化，需要重新适配。',
    );
  }

  const ids = new Set<string>();
  const conversations: XianyuChatConversation[] = [];
  let missingFields = 0;
  for (const rawConversation of page.conversations) {
    if (
      !isRecord(rawConversation) ||
      typeof rawConversation.conversation_id !== 'string' ||
      !rawConversation.conversation_id.trim() ||
      ids.has(rawConversation.conversation_id)
    ) {
      return failed(
        connection,
        page,
        timestamp.value,
        'PAGE_CHANGED',
        '闲鱼页面已变化，需要重新适配。',
      );
    }
    ids.add(rawConversation.conversation_id);
    const conversation: XianyuChatConversation = {
      conversation_id: rawConversation.conversation_id,
      avatar_ref: optionalString(rawConversation.avatar_ref),
      nickname: optionalString(rawConversation.nickname),
      last_message_summary: optionalString(
        rawConversation.last_message_summary,
      ),
      last_message_at: optionalDate(rawConversation.last_message_at),
      unread_count: optionalUnreadCount(rawConversation.unread_count),
      is_pinned: optionalBoolean(rawConversation.is_pinned),
      is_muted: optionalBoolean(rawConversation.is_muted),
    };
    missingFields += MAPPED_FIELDS.filter(
      (field) => conversation[field] === null,
    ).length;
    conversations.push(conversation);
  }

  const denominator = conversations.length * MAPPED_FIELDS.length;
  const missingFieldRatio = denominator === 0 ? 0 : missingFields / denominator;
  if (missingFieldRatio > XIANYU_CHAT_LIST_MISSING_FIELD_LIMIT) {
    return failed(
      connection,
      page,
      timestamp.value,
      'FIELD_COVERAGE_TOO_LOW',
      '闲鱼页面字段缺失过多，需要重新适配。',
    );
  }

  const sorted = sortConversations(conversations);
  return {
    schema_version: XIANYU_CHAT_LIST_SCHEMA_VERSION,
    result: 'SUCCESS',
    connection_id: connection.connection_id,
    source_page_version: XIANYU_LOCAL_PAGE_VERSION,
    read_at: timestamp.value,
    truncated: page.has_more || sorted.length > XIANYU_CHAT_LIST_MAX,
    missing_field_ratio: missingFieldRatio,
    conversations: sorted.slice(0, XIANYU_CHAT_LIST_MAX),
  };
}

function parseConversation(value: unknown): XianyuChatConversation | null {
  if (!isRecord(value) || !hasExactFields(value, CONVERSATION_FIELDS)) {
    return null;
  }
  if (
    typeof value.conversation_id !== 'string' ||
    !value.conversation_id.trim() ||
    (value.avatar_ref !== null && typeof value.avatar_ref !== 'string') ||
    (value.nickname !== null && typeof value.nickname !== 'string') ||
    (value.last_message_summary !== null &&
      typeof value.last_message_summary !== 'string') ||
    (value.last_message_at !== null && !isIsoDate(value.last_message_at)) ||
    (value.unread_count !== null &&
      (typeof value.unread_count !== 'number' ||
        !Number.isInteger(value.unread_count) ||
        value.unread_count < 0)) ||
    (value.is_pinned !== null && typeof value.is_pinned !== 'boolean') ||
    (value.is_muted !== null && typeof value.is_muted !== 'boolean')
  ) {
    return null;
  }
  return value as XianyuChatConversation;
}

export function parseLocalXianyuChatListSnapshot(
  raw: string | null,
): XianyuChatListReadSuccess | null {
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (
      !isRecord(parsed) ||
      !hasExactFields(parsed, CHAT_LIST_FIELDS) ||
      parsed.schema_version !== XIANYU_CHAT_LIST_SCHEMA_VERSION ||
      parsed.result !== 'SUCCESS' ||
      typeof parsed.connection_id !== 'string' ||
      !parsed.connection_id ||
      parsed.source_page_version !== XIANYU_LOCAL_PAGE_VERSION ||
      !isIsoDate(parsed.read_at) ||
      typeof parsed.truncated !== 'boolean' ||
      typeof parsed.missing_field_ratio !== 'number' ||
      !Number.isFinite(parsed.missing_field_ratio) ||
      parsed.missing_field_ratio < 0 ||
      parsed.missing_field_ratio > XIANYU_CHAT_LIST_MISSING_FIELD_LIMIT ||
      !Array.isArray(parsed.conversations) ||
      parsed.conversations.length > XIANYU_CHAT_LIST_MAX
    ) {
      return null;
    }
    const conversations = parsed.conversations.map(parseConversation);
    if (conversations.some((conversation) => conversation === null)) {
      return null;
    }
    const ids = new Set(
      conversations.map((conversation) => conversation?.conversation_id),
    );
    if (ids.size !== conversations.length) return null;
    return {
      ...(parsed as Omit<XianyuChatListReadSuccess, 'conversations'>),
      conversations: conversations as XianyuChatConversation[],
    };
  } catch {
    return null;
  }
}

type LocalChatListListener = () => void;
const listeners = new Set<LocalChatListListener>();
let cachedStorage: Storage | null | undefined;
let cachedRaw: string | null | undefined;
let cachedSnapshot: XianyuChatListReadSuccess | null = null;

export function readStoredLocalXianyuChatList(): XianyuChatListReadSuccess | null {
  if (typeof window === 'undefined') return null;
  const storage = window.sessionStorage;
  if (cachedStorage !== storage) {
    cachedStorage = storage;
    cachedRaw = undefined;
    cachedSnapshot = null;
  }
  const raw = storage.getItem(XIANYU_CHAT_LIST_STORAGE_KEY);
  if (raw === cachedRaw) return cachedSnapshot;
  const snapshot = parseLocalXianyuChatListSnapshot(raw);
  if (!snapshot && raw !== null) {
    storage.removeItem(XIANYU_CHAT_LIST_STORAGE_KEY);
  }
  cachedRaw = snapshot ? raw : null;
  cachedSnapshot = snapshot;
  return snapshot;
}

export function writeLocalXianyuChatList(
  snapshot: XianyuChatListReadSuccess,
): void {
  const serialized = JSON.stringify(snapshot);
  window.sessionStorage.setItem(XIANYU_CHAT_LIST_STORAGE_KEY, serialized);
  cachedStorage = window.sessionStorage;
  cachedRaw = serialized;
  cachedSnapshot = snapshot;
  listeners.forEach((listener) => listener());
}

export function clearLocalXianyuChatList(): void {
  if (typeof window !== 'undefined') {
    window.sessionStorage.removeItem(XIANYU_CHAT_LIST_STORAGE_KEY);
    cachedStorage = window.sessionStorage;
    cachedRaw = null;
    cachedSnapshot = null;
    listeners.forEach((listener) => listener());
  }
}

export function subscribeLocalXianyuChatList(
  listener: LocalChatListListener,
): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
