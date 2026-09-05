'use client';

import {
  createContext,
  useContext,
  useSyncExternalStore,
  type ReactNode,
} from 'react';

import { logoutAuthSession } from '@/lib/api';
import {
  type AuthArea,
  type AuthSessionData,
  clearAuthSession,
  readAuthSession,
  storeAuthSession,
  subscribeAuthSessions,
} from '@/lib/auth-session';

type AuthContextValue = {
  ready: boolean;
  customer: AuthSessionData | null;
  staff: AuthSessionData | null;
  saveSession: (session: AuthSessionData) => void;
  logout: (area: AuthArea) => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);
const subscribeHydration = () => () => undefined;
const hydratedSnapshot = () => true;
const serverHydratedSnapshot = () => false;
const emptySessionSnapshot = () => null;

export function AuthProvider({ children }: { children: ReactNode }) {
  const ready = useSyncExternalStore(
    subscribeHydration,
    hydratedSnapshot,
    serverHydratedSnapshot,
  );
  const customer = useSyncExternalStore(
    subscribeAuthSessions,
    () => readAuthSession('customer'),
    emptySessionSnapshot,
  );
  const staff = useSyncExternalStore(
    subscribeAuthSessions,
    () => readAuthSession('staff'),
    emptySessionSnapshot,
  );

  const value: AuthContextValue = {
    ready,
    customer,
    staff,
    saveSession(session) {
      const area =
        session.principal.principal_type === 'CUSTOMER' ? 'customer' : 'staff';
      storeAuthSession(area, session);
    },
    async logout(area) {
      const session = area === 'customer' ? customer : staff;
      try {
        if (session) await logoutAuthSession(session.access_token);
      } finally {
        clearAuthSession(area);
      }
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}
