import { clientId } from './client-id.ts';

export const XIANYU_EXPERIMENT_NOTICE =
  '实验性闲鱼个人账号连接，仅供本人授权的本地测试';
export const XIANYU_LOCAL_PAGE_VERSION = 'local-fixed-page-v1';
export const XIANYU_CONNECTION_STORAGE_KEY =
  'harbor-support-xianyu-local-connection';

export const XIANYU_OFFICIAL_PAGE_URL = 'https://www.goofish.com/';

export type XianyuFixtureId = 'account-a' | 'account-b';

export type XianyuLocalFixture = {
  id: XianyuFixtureId;
  display_identifier: string;
};

export const XIANYU_LOCAL_FIXTURES: readonly XianyuLocalFixture[] = [
  { id: 'account-a', display_identifier: '本地模拟账号 A' },
  { id: 'account-b', display_identifier: '本地模拟账号 B' },
];

export type XianyuConnectionStatus = 'CONNECTED' | 'REAUTH_REQUIRED';

export type XianyuLocalConnection = {
  schema_version: 1;
  provider: 'XIANYU';
  connection_id: string;
  display_identifier: string;
  source_page: 'LOCAL_FIXED_PAGE';
  source_page_version: typeof XIANYU_LOCAL_PAGE_VERSION;
  status: XianyuConnectionStatus;
  consented_at: string;
  connected_at: string;
  last_synced_at: string;
};

export type XianyuConnectedLocalConnection = Omit<
  XianyuLocalConnection,
  'status'
> & { status: 'CONNECTED' };

const CONNECTION_FIELDS = [
  'schema_version',
  'provider',
  'connection_id',
  'display_identifier',
  'source_page',
  'source_page_version',
  'status',
  'consented_at',
  'connected_at',
  'last_synced_at',
] as const;

type LocalConnectionListener = () => void;

const listeners = new Set<LocalConnectionListener>();
let cachedStorage: Storage | null | undefined;
let cachedRaw: string | null | undefined;
let cachedConnection: XianyuLocalConnection | null = null;

function fixtureFor(id: XianyuFixtureId) {
  const fixture = XIANYU_LOCAL_FIXTURES.find((item) => item.id === id);
  if (!fixture) throw new Error('本地固定页面不存在');
  return fixture;
}

function isIsoDate(value: unknown): value is string {
  return typeof value === 'string' && Number.isFinite(Date.parse(value));
}

export function createLocalXianyuConnection(
  fixtureId: XianyuFixtureId,
  options: { consentedAt?: string; now?: string } = {},
): XianyuConnectedLocalConnection {
  const fixture = fixtureFor(fixtureId);
  const now = options.now ?? new Date().toISOString();
  const consentedAt = options.consentedAt ?? now;
  if (!isIsoDate(now) || !isIsoDate(consentedAt)) {
    throw new Error('本地连接时间无效');
  }
  return {
    schema_version: 1,
    provider: 'XIANYU',
    connection_id: clientId('connection'),
    display_identifier: fixture.display_identifier,
    source_page: 'LOCAL_FIXED_PAGE',
    source_page_version: XIANYU_LOCAL_PAGE_VERSION,
    status: 'CONNECTED',
    consented_at: consentedAt,
    connected_at: now,
    last_synced_at: now,
  };
}

function isConnectionStatus(value: unknown): value is XianyuConnectionStatus {
  return value === 'CONNECTED' || value === 'REAUTH_REQUIRED';
}

function isKnownDisplayIdentifier(value: unknown): value is string {
  return XIANYU_LOCAL_FIXTURES.some(
    (fixture) => fixture.display_identifier === value,
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function parseLocalXianyuConnection(
  raw: string | null,
): XianyuLocalConnection | null {
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!isRecord(parsed)) return null;
    const fields = Object.keys(parsed);
    if (
      fields.length !== CONNECTION_FIELDS.length ||
      CONNECTION_FIELDS.some((field) => !Object.hasOwn(parsed, field))
    ) {
      return null;
    }
    if (
      parsed.schema_version !== 1 ||
      parsed.provider !== 'XIANYU' ||
      typeof parsed.connection_id !== 'string' ||
      !parsed.connection_id ||
      !isKnownDisplayIdentifier(parsed.display_identifier) ||
      parsed.source_page !== 'LOCAL_FIXED_PAGE' ||
      parsed.source_page_version !== XIANYU_LOCAL_PAGE_VERSION ||
      !isConnectionStatus(parsed.status) ||
      !isIsoDate(parsed.consented_at) ||
      !isIsoDate(parsed.connected_at) ||
      !isIsoDate(parsed.last_synced_at)
    ) {
      return null;
    }
    return parsed as XianyuLocalConnection;
  } catch {
    return null;
  }
}

export function markXianyuReauthRequired(
  connection: XianyuLocalConnection,
): XianyuLocalConnection {
  if (connection.status !== 'CONNECTED') {
    throw new Error('该连接已经处于重新登录状态');
  }
  return { ...connection, status: 'REAUTH_REQUIRED' };
}

export function readLocalXianyuConnection(): XianyuLocalConnection | null {
  if (typeof window === 'undefined') return null;
  const storage = window.sessionStorage;
  if (cachedStorage !== storage) {
    cachedStorage = storage;
    cachedRaw = undefined;
    cachedConnection = null;
  }
  const raw = storage.getItem(XIANYU_CONNECTION_STORAGE_KEY);
  if (raw === cachedRaw) return cachedConnection;
  const connection = parseLocalXianyuConnection(raw);
  if (!connection && raw !== null) {
    storage.removeItem(XIANYU_CONNECTION_STORAGE_KEY);
  }
  cachedRaw = connection ? raw : null;
  cachedConnection = connection;
  return connection;
}

export function writeLocalXianyuConnection(
  connection: XianyuLocalConnection,
): void {
  const serialized = JSON.stringify(connection);
  window.sessionStorage.setItem(XIANYU_CONNECTION_STORAGE_KEY, serialized);
  cachedStorage = window.sessionStorage;
  cachedRaw = serialized;
  cachedConnection = connection;
  listeners.forEach((listener) => listener());
}

export function clearLocalXianyuConnection(): void {
  if (typeof window !== 'undefined') {
    window.sessionStorage.removeItem(XIANYU_CONNECTION_STORAGE_KEY);
    cachedStorage = window.sessionStorage;
    cachedRaw = null;
    cachedConnection = null;
    listeners.forEach((listener) => listener());
  }
}

export function subscribeLocalXianyuConnection(
  listener: LocalConnectionListener,
): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
