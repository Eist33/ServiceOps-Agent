'use client';

import { useSyncExternalStore, useState } from 'react';
import {
  CheckCircle2,
  CircleAlert,
  ExternalLink,
  KeyRound,
  Link2,
  LogOut,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react';

import { StaffNavigation } from '@/app/staff/staff-navigation';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  XIANYU_EXPERIMENT_NOTICE,
  XIANYU_LOCAL_FIXTURES,
  XIANYU_OFFICIAL_PAGE_URL,
  clearLocalXianyuConnection,
  createLocalXianyuConnection,
  markXianyuReauthRequired,
  readLocalXianyuConnection,
  subscribeLocalXianyuConnection,
  writeLocalXianyuConnection,
  type XianyuConnectionStatus,
  type XianyuFixtureId,
  type XianyuLocalConnection,
} from '@/lib/xianyu-local-session';

export default function XianyuChannelClient() {
  const connection = useSyncExternalStore(
    subscribeLocalXianyuConnection,
    readLocalXianyuConnection,
    () => null,
  );
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  function connectLocalFixture(fixtureId: XianyuFixtureId) {
    if (!consent) {
      setNotice('');
      setError('请先阅读并同意实验告知，才能建立本地模拟连接。');
      return;
    }
    setError('');
    const next = createLocalXianyuConnection(fixtureId);
    writeLocalXianyuConnection(next);
    setNotice(
      `已连接 ${next.display_identifier}。当前仅保留本地只读连接元数据。`,
    );
  }

  function markReauthRequired() {
    const connectedConnection = connection;
    if (!connectedConnection || connectedConnection.status !== 'CONNECTED')
      return;
    const next = markXianyuReauthRequired(connectedConnection);
    writeLocalXianyuConnection(next);
    setError(
      '当前页面或账号状态无法确认，连接已失败关闭；请由用户重新完成可见登录。',
    );
    setNotice('');
  }

  function reauthenticate() {
    clearLocalXianyuConnection();
    setConsent(false);
    setError('旧连接已清除。请重新阅读实验告知，再开始一次可见登录。');
    setNotice('');
  }

  function disconnect() {
    clearLocalXianyuConnection();
    setConsent(false);
    setError('');
    setNotice('已退出并清除本地连接数据。');
  }

  const status = connection?.status ?? 'DISCONNECTED';

  return (
    <main className="min-h-screen bg-[#f4f7f8] text-foreground">
      <header className="border-b bg-white">
        <div className="mx-auto flex min-h-16 max-w-[1500px] flex-wrap items-center justify-between gap-3 px-4 py-3 lg:px-8">
          <div className="flex items-center gap-3">
            <span className="grid size-9 place-items-center rounded-xl bg-primary text-primary-foreground">
              <Link2 className="size-4.5" />
            </span>
            <div>
              <p className="text-sm font-semibold">Harbor Channels</p>
              <p className="text-[11px] text-muted-foreground">
                渠道账号 · 本地实验
              </p>
            </div>
          </div>
          <StaffNavigation active="channel" />
        </div>
      </header>

      <div className="mx-auto max-w-[1100px] space-y-6 px-4 py-7 lg:px-8">
        <section className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <div>
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-primary">
              <ShieldCheck className="size-4" /> 客服后台 · 用户可见授权
            </div>
            <h1 className="text-2xl font-semibold tracking-tight">
              闲鱼实验连接
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              仅验证本人控制的可见页面登录边界。产品不会代填手机号或验证码，也不会读取、保存或上传闲鱼
              Cookie、Token 和页面报文。
            </p>
          </div>
          <Badge
            className="w-fit bg-amber-50 text-amber-800"
            variant="secondary"
          >
            实验性 · 仅本地
          </Badge>
        </section>

        {(error || notice) && (
          <div
            className={`flex items-start gap-2 rounded-xl border px-4 py-3 text-sm ${
              error
                ? 'border-red-100 bg-red-50 text-red-700'
                : 'border-emerald-100 bg-emerald-50 text-emerald-800'
            }`}
            role={error ? 'alert' : 'status'}
          >
            {error ? (
              <CircleAlert className="mt-0.5 size-4 shrink-0" />
            ) : (
              <CheckCircle2 className="mt-0.5 size-4 shrink-0" />
            )}
            <span>{error || notice}</span>
          </div>
        )}

        <Alert className="border-amber-200 bg-amber-50/70">
          <ShieldAlert className="text-amber-700" />
          <AlertTitle>{XIANYU_EXPERIMENT_NOTICE}</AlertTitle>
          <AlertDescription>
            首版只允许本地固定页面模拟连接；真实页面必须由用户在新窗口中亲自操作。未同意、未登录、需要验证、页面结构变化或账号身份无法确认时，系统不建立连接并停止后续读取。
          </AlertDescription>
        </Alert>

        <section className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
          <Card aria-label="闲鱼实验连接">
            <CardHeader className="border-b">
              <CardTitle className="flex items-center gap-2">
                <Link2 className="size-5 text-primary" /> 连接状态
              </CardTitle>
              <CardDescription>
                连接只存在于当前浏览器标签页的 sessionStorage，不进入客服 API
                或数据库。
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5 pt-5">
              <ConnectionSummary connection={connection} status={status} />

              {connection?.status === 'CONNECTED' ? (
                <ConnectedActions
                  onMarkReauthRequired={markReauthRequired}
                  onDisconnect={disconnect}
                />
              ) : connection?.status === 'REAUTH_REQUIRED' ? (
                <div className="space-y-3 rounded-xl border border-red-200 bg-red-50 p-4">
                  <p className="text-sm font-semibold text-red-800">
                    已失败关闭，不能继续读取
                  </p>
                  <p className="text-xs leading-5 text-red-700">
                    当前连接的页面或身份证据不再可信。请先清除旧连接，再由用户重新打开页面并完成登录。
                  </p>
                  <Button onClick={reauthenticate} variant="destructive">
                    <RefreshCw /> 重新登录
                  </Button>
                </div>
              ) : (
                <LoginBoundary
                  consent={consent}
                  onConsentChange={setConsent}
                  onConnectFixture={connectLocalFixture}
                  onRealPageIdentityUnknown={() => {
                    setNotice('');
                    setError(
                      '当前真实页面的账号无法由本地实验确认，已失败关闭；不会读取页面数据。',
                    );
                  }}
                />
              )}
            </CardContent>
          </Card>

          <Card className="h-fit">
            <CardHeader className="border-b">
              <CardTitle className="flex items-center gap-2">
                <KeyRound className="size-5 text-primary" /> 本地存储边界
              </CardTitle>
              <CardDescription>
                连接元数据示例（不是真实登录凭据）
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 pt-5 text-xs leading-5 text-muted-foreground">
              <p>保存：连接 ID、固定页面版本、脱敏账号标识、连接状态和时间。</p>
              <p>
                不保存：手机号、短信验证码、Cookie、Token、设备标识、完整登录报文或原始页面数据。
              </p>
              <p>
                退出或重新登录会先删除旧连接；切换账号不会复用旧账号状态。关闭标签页后，标签页级会话也随之消失。
              </p>
              <div className="rounded-lg bg-slate-50 p-3 font-mono text-[11px] text-slate-600">
                <p>存储键：harbor-support-xianyu-local-connection</p>
                <p className="mt-1">来源：LOCAL_FIXED_PAGE / v1</p>
              </div>
            </CardContent>
          </Card>
        </section>
      </div>
    </main>
  );
}

function ConnectionSummary({
  connection,
  status,
}: {
  connection: XianyuLocalConnection | null;
  status: XianyuConnectionStatus | 'DISCONNECTED';
}) {
  const statusConfig = {
    DISCONNECTED: ['未连接', 'bg-slate-100 text-slate-700'],
    CONNECTED: ['已连接（本地）', 'bg-emerald-50 text-emerald-700'],
    REAUTH_REQUIRED: ['需要重新登录', 'bg-red-50 text-red-700'],
  }[status];

  return (
    <dl className="grid gap-4 rounded-xl border bg-[#fbfcfc] p-4 sm:grid-cols-3">
      <div>
        <dt className="text-xs text-muted-foreground">当前账号</dt>
        <dd className="mt-1 font-semibold">
          {connection?.display_identifier ?? '未识别'}
        </dd>
      </div>
      <div>
        <dt className="text-xs text-muted-foreground">连接状态</dt>
        <dd className="mt-1">
          <Badge className={statusConfig[1]} variant="secondary">
            {statusConfig[0]}
          </Badge>
        </dd>
      </div>
      <div>
        <dt className="text-xs text-muted-foreground">最后同步时间</dt>
        <dd className="mt-1 font-semibold">
          {connection
            ? new Date(connection.last_synced_at).toLocaleString('zh-CN')
            : '暂无'}
        </dd>
      </div>
      {connection && (
        <div className="sm:col-span-3 border-t pt-3 text-xs text-muted-foreground">
          本地连接 ID：{connection.connection_id.slice(0, 8)}… · 来源页面版本：
          {connection.source_page_version}
        </div>
      )}
    </dl>
  );
}

function LoginBoundary({
  consent,
  onConsentChange,
  onConnectFixture,
  onRealPageIdentityUnknown,
}: {
  consent: boolean;
  onConsentChange: (value: boolean) => void;
  onConnectFixture: (fixtureId: XianyuFixtureId) => void;
  onRealPageIdentityUnknown: () => void;
}) {
  return (
    <div className="space-y-5">
      <div className="rounded-xl border bg-white p-4">
        <p className="text-sm font-semibold">1. 用户亲自打开可见页面</p>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          点击后会打开官方页面；手机号、短信验证码、图形验证、滑块和设备确认全部由用户在该页面完成。
        </p>
        <a
          className={`${buttonVariants({ variant: 'outline' })} mt-4`}
          href={XIANYU_OFFICIAL_PAGE_URL}
          rel="noreferrer"
          target="_blank"
        >
          <ExternalLink /> 打开官方闲鱼页面
        </a>
      </div>

      <label className="flex items-start gap-3 rounded-xl border bg-slate-50 p-4 text-sm">
        <input
          aria-label="同意闲鱼本地实验告知"
          checked={consent}
          className="mt-0.5 size-4 accent-primary"
          onChange={(event) => onConsentChange(event.target.checked)}
          type="checkbox"
        />
        <span>
          我已阅读并同意只在本人授权的本地环境进行只读实验，理解产品不会代替登录、读取验证码或执行任何聊天/订单写操作。
        </span>
      </label>

      <div className="rounded-xl border border-sky-100 bg-sky-50/60 p-4">
        <p className="text-sm font-semibold text-sky-900">
          2. 本地固定页面模拟（自动化测试）
        </p>
        <p className="mt-1 text-xs leading-5 text-sky-800">
          固定页面不会访问闲鱼，也不包含手机号、验证码、Cookie 或
          Token。选择后只保存脱敏模拟账号标识，用于验证连接、刷新、失效和切换边界。
        </p>
        <div className="mt-4 grid gap-2 sm:grid-cols-2">
          {XIANYU_LOCAL_FIXTURES.map((fixture) => (
            <Button
              key={fixture.id}
              onClick={() => onConnectFixture(fixture.id)}
              variant="secondary"
            >
              <ShieldCheck /> 连接{fixture.display_identifier}
            </Button>
          ))}
        </div>
      </div>

      <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4">
        <CircleAlert className="mt-0.5 size-4 shrink-0 text-amber-700" />
        <div className="text-xs leading-5 text-amber-800">
          <p className="font-semibold">真实页面不会自动变成已连接</p>
          <p className="mt-1">
            当前没有官方身份验证或可信页面桥接。即使用户完成真实页面登录，本地实验也会因无法确认账号而失败关闭；请勿把手机号或验证码复制到本产品。
          </p>
          <Button
            className="mt-3"
            onClick={onRealPageIdentityUnknown}
            size="sm"
            variant="outline"
          >
            当前账号无法确认，停止连接
          </Button>
        </div>
      </div>
    </div>
  );
}

function ConnectedActions({
  onMarkReauthRequired,
  onDisconnect,
}: {
  onMarkReauthRequired: () => void;
  onDisconnect: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button onClick={onMarkReauthRequired} variant="outline">
        <ShieldAlert /> 页面/身份不确定
      </Button>
      <Button onClick={onDisconnect} variant="destructive">
        <LogOut /> 退出并清除本地连接
      </Button>
    </div>
  );
}
