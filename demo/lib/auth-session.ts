import { clearLocalXianyuExperimentData } from './xianyu-local-lifecycle';

export type AuthArea = 'customer' | 'staff';

export type AuthPrincipal = {
  account_id: string;
  provider: string;
  principal_type: 'CUSTOMER' | 'OPERATOR';
  principal_id: string;
  display_name: string;
  role:
    | 'CUSTOMER'
    | 'SUPPORT_AGENT'
    | 'KNOWLEDGE_MANAGER'
    | 'OPERATIONS_MANAGER';
};

export type AuthSessionData = {
  access_token: string;
  token_type: 'bearer';
  expires_at: string;
  principal: AuthPrincipal;
};

const STORAGE_KEYS: Record<AuthArea, string> = {
  customer: 'harbor-support-customer-auth',
  staff: 'harbor-support-staff-auth',
};

const listeners = new Set<() => void>();
const cache: Record<
  AuthArea,
  { raw: string | null; value: AuthSessionData | null }
> = {
  customer: { raw: null, value: null },
  staff: { raw: null, value: null },
};

function expectedPrincipalType(area: AuthArea) {
  return area === 'customer' ? 'CUSTOMER' : 'OPERATOR';
}

function invalidateStoredSession(area: AuthArea): void {
  if (area === 'staff') clearLocalXianyuExperimentData();
  window.sessionStorage.removeItem(STORAGE_KEYS[area]);
  cache[area] = { raw: null, value: null };
}

export function readAuthSession(area: AuthArea): AuthSessionData | null {
  if (typeof window === 'undefined') return null;
  const raw = window.sessionStorage.getItem(STORAGE_KEYS[area]);
  if (cache[area].raw === raw) return cache[area].value;
  if (!raw) return null;
  try {
    const session = JSON.parse(raw) as AuthSessionData;
    if (
      !session.access_token ||
      !session.expires_at ||
      session.principal?.principal_type !== expectedPrincipalType(area) ||
      Date.parse(session.expires_at) <= Date.now()
    ) {
      invalidateStoredSession(area);
      return null;
    }
    cache[area] = { raw, value: session };
    return session;
  } catch {
    invalidateStoredSession(area);
    return null;
  }
}

export function storeAuthSession(area: AuthArea, session: AuthSessionData) {
  const raw = JSON.stringify(session);
  window.sessionStorage.setItem(STORAGE_KEYS[area], raw);
  cache[area] = { raw, value: session };
  listeners.forEach((listener) => listener());
}

export function clearAuthSession(area: AuthArea) {
  if (typeof window !== 'undefined') {
    if (area === 'staff') clearLocalXianyuExperimentData();
    window.sessionStorage.removeItem(STORAGE_KEYS[area]);
    cache[area] = { raw: null, value: null };
    listeners.forEach((listener) => listener());
  }
}

export function subscribeAuthSessions(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function bearerHeaders(area: AuthArea): Record<string, string> {
  const session = readAuthSession(area);
  return session ? { Authorization: `Bearer ${session.access_token}` } : {};
}
