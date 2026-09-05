'use client';

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Headphones, Loader2, LockKeyhole, ShieldCheck } from 'lucide-react';

import { useAuth } from '@/components/auth-provider';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  type DevelopmentAccountData,
  listDevelopmentAccounts,
  loginDevelopmentAccount,
} from '@/lib/api';
import type { AuthArea, AuthSessionData } from '@/lib/auth-session';
import { clearLocalXianyuExperimentData } from '@/lib/xianyu-local-lifecycle';

const roleLabels: Record<string, string> = {
  CUSTOMER: '客户',
  SUPPORT_AGENT: '客服坐席',
  KNOWLEDGE_MANAGER: '知识与运营管理员',
  OPERATIONS_MANAGER: '运营管理员',
};

export function AuthGate({
  area,
  allowedRoles,
  children,
}: {
  area: AuthArea;
  allowedRoles?: string[];
  children: ReactNode;
}) {
  const auth = useAuth();
  const session = area === 'customer' ? auth.customer : auth.staff;

  if (!auth.ready) return <AuthLoading />;
  if (!session) return <LoginSurface area={area} />;
  if (allowedRoles && !allowedRoles.includes(session.principal.role)) {
    return <AccessDenied area={area} session={session} />;
  }
  return children;
}

function AuthLoading() {
  return (
    <main className="grid min-h-screen place-items-center bg-[#f4f7f8] text-sm text-muted-foreground">
      <span className="flex items-center gap-2">
        <Loader2 className="size-4 animate-spin" /> 正在检查登录状态…
      </span>
    </main>
  );
}

function LoginSurface({ area }: { area: AuthArea }) {
  const { saveSession } = useAuth();
  const [accounts, setAccounts] = useState<DevelopmentAccountData[]>([]);
  const [selected, setSelected] = useState('');
  const [password, setPassword] = useState('serviceops');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const expectedType = area === 'customer' ? 'CUSTOMER' : 'OPERATOR';

  useEffect(() => {
    let cancelled = false;
    void listDevelopmentAccounts()
      .then((items) => {
        if (cancelled) return;
        const filtered = items.filter(
          (item) => item.principal_type === expectedType,
        );
        setAccounts(filtered);
        setSelected(filtered[0]?.login_name ?? '');
      })
      .catch((caught) => {
        if (!cancelled) {
          setError(
            caught instanceof Error ? caught.message : '开发账号加载失败',
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [expectedType]);

  const selectedAccount = useMemo(
    () => accounts.find((account) => account.login_name === selected),
    [accounts, selected],
  );

  async function submit(event: { preventDefault(): void }) {
    event.preventDefault();
    if (!selected || !password || busy) return;
    setBusy(true);
    setError('');
    try {
      const session = await loginDevelopmentAccount(selected, password);
      if (session.principal.principal_type !== expectedType) {
        throw new Error('所选账号不能进入当前区域');
      }
      if (area === 'staff') {
        clearLocalXianyuExperimentData();
      }
      saveSession(session);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '登录失败');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-[radial-gradient(circle_at_top_left,#e7f3f4_0,transparent_34%),linear-gradient(145deg,#f7fafb,#eef3f5)] px-4 py-10 text-foreground">
      <Card className="w-full max-w-lg border-slate-200 bg-white/95 shadow-xl shadow-slate-900/5">
        <CardHeader className="space-y-4 border-b">
          <span className="grid size-11 place-items-center rounded-2xl bg-primary text-primary-foreground">
            {area === 'customer' ? (
              <Headphones className="size-5" />
            ) : (
              <ShieldCheck className="size-5" />
            )}
          </span>
          <div>
            <CardTitle className="text-xl">
              <h1>{area === 'customer' ? '登录客户服务' : '登录客服后台'}</h1>
            </CardTitle>
            <CardDescription className="mt-2 text-sm leading-6">
              当前为开发环境，请使用已有模拟账号。正式环境将由平台授权身份替换。
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="pt-6">
          <form className="space-y-5" onSubmit={submit}>
            <fieldset disabled={loading || busy}>
              <legend className="mb-2 text-sm font-medium">选择开发账号</legend>
              <div className="grid gap-2 sm:grid-cols-2">
                {accounts.map((account) => (
                  <button
                    aria-pressed={selected === account.login_name}
                    className={`rounded-xl border p-3 text-left transition ${selected === account.login_name ? 'border-primary bg-primary/5 ring-1 ring-primary/20' : 'hover:border-slate-400'}`}
                    key={account.login_name}
                    onClick={() => setSelected(account.login_name)}
                    type="button"
                  >
                    <span className="block text-sm font-semibold">
                      {account.display_name}
                    </span>
                    <span className="mt-1 block text-xs text-muted-foreground">
                      {roleLabels[account.role] ?? account.role} ·{' '}
                      {account.login_name}
                    </span>
                  </button>
                ))}
              </div>
            </fieldset>
            <div className="space-y-2">
              <Label htmlFor={`${area}-development-password`}>
                开发环境密码
              </Label>
              <Input
                autoComplete="current-password"
                id={`${area}-development-password`}
                onChange={(event) => setPassword(event.target.value)}
                type="password"
                value={password}
              />
              <p className="text-xs text-muted-foreground">
                本地默认密码为 serviceops，可通过环境配置修改。
              </p>
            </div>
            {selectedAccount && (
              <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
                将以 {selectedAccount.display_name} 身份进入
                {area === 'customer' ? '客户服务页面' : '受权限保护的客服后台'}
                。
              </p>
            )}
            {error && (
              <Alert variant="destructive">
                <LockKeyhole />
                <AlertTitle>无法登录</AlertTitle>
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <Button
              className="w-full"
              disabled={!selected || !password || busy || loading}
              type="submit"
            >
              {busy && <Loader2 className="animate-spin" />}
              {area === 'customer' ? '登录客户服务' : '登录客服后台'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}

function AccessDenied({
  area,
  session,
}: {
  area: AuthArea;
  session: AuthSessionData;
}) {
  const { logout } = useAuth();
  const target =
    session.principal.role === 'SUPPORT_AGENT'
      ? '/staff/agent'
      : '/staff/knowledge';
  return (
    <main className="grid min-h-screen place-items-center bg-[#f4f7f8] px-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>
            <h1>当前账号无权访问</h1>
          </CardTitle>
          <CardDescription>
            {session.principal.display_name} 当前角色为{' '}
            {roleLabels[session.principal.role] ?? session.principal.role}。
          </CardDescription>
        </CardHeader>
        <CardContent className="flex gap-2">
          {area === 'staff' && (
            <Button onClick={() => window.location.assign(target)}>
              进入可用工作区
            </Button>
          )}
          <Button onClick={() => void logout(area)} variant="outline">
            切换账号
          </Button>
        </CardContent>
      </Card>
    </main>
  );
}
