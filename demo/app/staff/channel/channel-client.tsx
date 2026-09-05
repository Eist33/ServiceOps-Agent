'use client';

import { useSyncExternalStore, useState } from 'react';
import {
  CheckCircle2,
  CircleAlert,
  ExternalLink,
  KeyRound,
  Link2,
  LogOut,
  MessageSquareText,
  Pin,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  VolumeX,
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
  getLocalXianyuChatPage,
  readLocalXianyuChatList,
  readStoredLocalXianyuChatList,
  subscribeLocalXianyuChatList,
  clearLocalXianyuChatList,
  writeLocalXianyuChatList,
  type XianyuChatListReadFailure,
  type XianyuChatListReadSuccess,
} from '@/lib/xianyu-chat-list';
import {
  clearLocalXianyuChatDetail,
  getLocalXianyuChatDetailPage,
  readLocalXianyuChatDetail,
  readStoredLocalXianyuChatDetail,
  subscribeLocalXianyuChatDetail,
  writeLocalXianyuChatDetail,
  type XianyuChatDetailReadFailure,
  type XianyuChatDetailReadSuccess,
} from '@/lib/xianyu-chat-detail';
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
  const storedChatList = useSyncExternalStore(
    subscribeLocalXianyuChatList,
    readStoredLocalXianyuChatList,
    () => null,
  );
  const storedChatDetail = useSyncExternalStore(
    subscribeLocalXianyuChatDetail,
    readStoredLocalXianyuChatDetail,
    () => null,
  );
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [chatFailure, setChatFailure] =
    useState<XianyuChatListReadFailure | null>(null);
  const [chatDetailFailure, setChatDetailFailure] =
    useState<XianyuChatDetailReadFailure | null>(null);

  const chatList =
    connection && storedChatList?.connection_id === connection.connection_id
      ? storedChatList
      : null;
  const chatDetail =
    connection &&
    chatList &&
    storedChatDetail?.connection_id === connection.connection_id &&
    chatList.conversations.some(
      (conversation) =>
        conversation.conversation_id === storedChatDetail.conversation_id,
    )
      ? storedChatDetail
      : null;

  function connectLocalFixture(fixtureId: XianyuFixtureId) {
    if (!consent) {
      setNotice('');
      setError('请先阅读并同意实验告知，才能建立本地模拟连接。');
      return;
    }
    setError('');
    clearLocalXianyuChatList();
    clearLocalXianyuChatDetail();
    setChatFailure(null);
    setChatDetailFailure(null);
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
    clearLocalXianyuChatDetail();
    setChatDetailFailure(null);
    setChatFailure(null);
    setError(
      '当前页面或账号状态无法确认，连接已失败关闭；请由用户重新完成可见登录。',
    );
    setNotice('');
  }

  function reauthenticate() {
    clearLocalXianyuConnection();
    clearLocalXianyuChatList();
    clearLocalXianyuChatDetail();
    setChatFailure(null);
    setChatDetailFailure(null);
    setConsent(false);
    setError('旧连接已清除。请重新阅读实验告知，再开始一次可见登录。');
    setNotice('');
  }

  function disconnect() {
    clearLocalXianyuConnection();
    clearLocalXianyuChatList();
    clearLocalXianyuChatDetail();
    setChatFailure(null);
    setChatDetailFailure(null);
    setConsent(false);
    setError('');
    setNotice('已退出并清除本地连接数据。');
  }

  function refreshChatList() {
    if (!connection || connection.status !== 'CONNECTED') return;
    const fixture = XIANYU_LOCAL_FIXTURES.find(
      (item) => item.display_identifier === connection.display_identifier,
    );
    if (!fixture) return;

    const result = readLocalXianyuChatList(
      connection,
      getLocalXianyuChatPage(fixture.id),
    );
    if (result.result === 'SUCCESS') {
      writeLocalXianyuChatList(result);
      setChatFailure(null);
      setError('');
      setNotice(`已读取 ${result.conversations.length} 个最近会话。`);
      return;
    }
    setChatFailure(result);
    setNotice('');
    setError(result.error_message);
  }

  function openChatDetail(conversationId: string) {
    if (!connection || connection.status !== 'CONNECTED' || !chatList) return;
    const fixture = XIANYU_LOCAL_FIXTURES.find(
      (item) => item.display_identifier === connection.display_identifier,
    );
    if (!fixture) return;

    const result = readLocalXianyuChatDetail(
      connection,
      chatList,
      conversationId,
      getLocalXianyuChatDetailPage(fixture.id, conversationId),
      {
        isConnectionStillValid: () => {
          const current = readLocalXianyuConnection();
          return (
            current?.connection_id === connection.connection_id &&
            current.status === 'CONNECTED'
          );
        },
      },
    );
    if (result.result === 'SUCCESS') {
      writeLocalXianyuChatDetail(result);
      setChatDetailFailure(null);
      setError('');
      setNotice(`已读取会话 ${conversationId} 的最近消息。`);
      return;
    }
    setChatDetailFailure(result);
    setNotice('');
    setError(result.error_message);
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

        {connection && (
          <ChatListPanel
            connection={connection}
            failure={chatFailure}
            onOpenDetail={openChatDetail}
            onRefresh={refreshChatList}
            snapshot={chatList}
          />
        )}
        {connection?.status === 'CONNECTED' && chatList && (
          <ChatDetailPanel
            connection={connection}
            failure={chatDetailFailure}
            snapshot={chatDetail}
          />
        )}
      </div>
    </main>
  );
}

function ChatListPanel({
  connection,
  failure,
  onOpenDetail,
  onRefresh,
  snapshot,
}: {
  connection: XianyuLocalConnection;
  failure: XianyuChatListReadFailure | null;
  onOpenDetail: (conversationId: string) => void;
  onRefresh: () => void;
  snapshot: XianyuChatListReadSuccess | null;
}) {
  const connected = connection.status === 'CONNECTED';
  return (
    <Card aria-label="闲鱼聊天列表只读映射">
      <CardHeader className="border-b">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              <MessageSquareText className="size-5 text-primary" />
              聊天列表（只读实验）
            </CardTitle>
            <CardDescription className="mt-2 max-w-2xl leading-5">
              首版只支持手动刷新当前本地固定页面，最多显示最近 20
              个会话；点击会话只读取最近历史消息，不发送消息或操作订单。
            </CardDescription>
          </div>
          <Badge className="bg-slate-100 text-slate-700" variant="secondary">
            LOCAL_FIXED_PAGE / v1 · 只读
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 pt-5">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-[#fbfcfc] p-4">
          <div className="text-xs leading-5 text-muted-foreground">
            <p>
              当前连接：
              <span className="font-semibold text-foreground">
                {connection.display_identifier}
              </span>
            </p>
            <p>
              只在当前标签页保留已确认的本地读取结果，连接 ID：
              {connection.connection_id.slice(0, 8)}…
            </p>
          </div>
          {connected ? (
            <Button onClick={onRefresh}>
              <RefreshCw /> 手动刷新聊天列表
            </Button>
          ) : (
            <Badge className="bg-red-50 text-red-700" variant="secondary">
              已停止读取
            </Badge>
          )}
        </div>

        {failure && (
          <div
            className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"
            role="alert"
          >
            <p className="font-semibold">本次读取失败，未标记为成功</p>
            <p className="mt-1 text-xs leading-5">{failure.error_message}</p>
            {snapshot && (
              <p className="mt-2 text-xs leading-5">
                上一份已确认列表仍保留，未被失败结果覆盖。
              </p>
            )}
          </div>
        )}

        {!connected ? (
          <p className="rounded-xl border border-red-100 bg-red-50/60 p-4 text-sm text-red-800">
            当前连接已失败关闭，聊天列表不会继续读取。请重新登录后再开始本地实验。
          </p>
        ) : !snapshot ? (
          <p className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">
            尚未读取当前页面的聊天列表。点击“手动刷新聊天列表”开始一次只读读取。
          </p>
        ) : snapshot.conversations.length === 0 ? (
          <p className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">
            当前页面没有最近会话。
          </p>
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
              <span>
                已读取 {snapshot.conversations.length} 个会话
                {snapshot.truncated ? '（仅显示前 20 条）' : ''}
              </span>
              <span>
                读取时间：{new Date(snapshot.read_at).toLocaleString('zh-CN')} ·
                页面版本：
                {snapshot.source_page_version}
              </span>
            </div>
            <ul className="divide-y rounded-xl border">
              {snapshot.conversations.map((conversation) => (
                <li
                  aria-label={`聊天会话 ${conversation.nickname ?? 'UNKNOWN'}`}
                  key={conversation.conversation_id}
                >
                  <button
                    aria-label={`查看聊天会话 ${conversation.nickname ?? 'UNKNOWN'}`}
                    className="flex w-full flex-col gap-3 p-4 text-left transition hover:bg-slate-50 sm:flex-row sm:items-center sm:justify-between"
                    onClick={() => onOpenDetail(conversation.conversation_id)}
                    type="button"
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      <span
                        aria-label={`头像 ${conversation.avatar_ref ?? 'UNKNOWN'}`}
                        className="grid size-10 shrink-0 place-items-center rounded-full bg-primary/10 text-sm font-semibold text-primary"
                      >
                        {(conversation.nickname ?? 'U').slice(0, 1)}
                      </span>
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="truncate text-sm font-semibold">
                            {conversation.nickname ?? 'UNKNOWN'}
                          </p>
                          {conversation.is_pinned === true && (
                            <Badge
                              className="gap-1 bg-amber-50 text-amber-800"
                              variant="secondary"
                            >
                              <Pin className="size-3" /> 置顶
                            </Badge>
                          )}
                          {conversation.is_muted === true && (
                            <Badge
                              className="gap-1 bg-slate-100 text-slate-700"
                              variant="secondary"
                            >
                              <VolumeX className="size-3" /> 静音
                            </Badge>
                          )}
                        </div>
                        <p className="mt-1 truncate text-xs text-muted-foreground">
                          {conversation.last_message_summary ?? 'UNKNOWN'}
                        </p>
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-3 text-xs text-muted-foreground sm:flex-col sm:items-end sm:gap-1">
                      <span>
                        {conversation.last_message_at
                          ? new Date(
                              conversation.last_message_at,
                            ).toLocaleString('zh-CN')
                          : 'UNKNOWN'}
                      </span>
                      <span className="font-medium text-foreground">
                        未读：{conversation.unread_count ?? 'UNKNOWN'}
                      </span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
            <p className="text-xs leading-5 text-muted-foreground">
              点击会话只读取当前连接下的本地固定历史消息。结果绑定当前连接
              ID；字段无法识别时显示 UNKNOWN，不猜测、不合并其他账号数据。
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ChatDetailPanel({
  connection,
  failure,
  snapshot,
}: {
  connection: XianyuLocalConnection;
  failure: XianyuChatDetailReadFailure | null;
  snapshot: XianyuChatDetailReadSuccess | null;
}) {
  return (
    <Card aria-label="闲鱼会话详情只读映射">
      <CardHeader className="border-b">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              <MessageSquareText className="size-5 text-primary" />
              会话详情（只读实验）
            </CardTitle>
            <CardDescription className="mt-2 max-w-2xl leading-5">
              只显示当前已确认会话的最近一段历史消息。文本和系统消息可读；图片、商品卡片、订单卡片及其他类型显示受控占位，不下载附件。
            </CardDescription>
          </div>
          <Badge className="bg-slate-100 text-slate-700" variant="secondary">
            当前标签页 · 只读
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 pt-5">
        {failure && (
          <div
            className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"
            role="alert"
          >
            <p className="font-semibold">本次详情读取失败，未保存本次结果</p>
            <p className="mt-1 text-xs leading-5">{failure.error_message}</p>
            {snapshot && (
              <p className="mt-2 text-xs leading-5">
                上一份已确认的会话详情仍保留，未被失败结果覆盖。
              </p>
            )}
          </div>
        )}

        {!snapshot ? (
          <p className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">
            点击上方聊天列表中的会话，读取当前连接下的最近历史消息。
          </p>
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
              <span>
                已读取 {snapshot.messages.length} 条消息
                {snapshot.truncated ? '（历史已截断）' : ''}
              </span>
              <span>
                会话：{snapshot.conversation_id} · 读取时间：
                {new Date(snapshot.read_at).toLocaleString('zh-CN')}
              </span>
            </div>
            <ul
              aria-label={`会话 ${snapshot.conversation_id} 的消息历史`}
              className="space-y-3"
            >
              {snapshot.messages.map((message) => (
                <li
                  aria-label={`消息 ${message.message_id}`}
                  className={`rounded-xl border p-4 ${message.sender === 'SELF' ? 'ml-8 bg-primary/5' : message.sender === 'SYSTEM' ? 'bg-slate-50' : 'mr-8 bg-white'}`}
                  key={message.message_id}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                    <span>
                      {message.sender === 'SELF'
                        ? '我方'
                        : message.sender === 'OTHER'
                          ? '对方'
                          : message.sender === 'SYSTEM'
                            ? '系统'
                            : 'UNKNOWN'}
                      {' · '}
                      {message.message_type}
                    </span>
                    <span>
                      {message.sent_at
                        ? new Date(message.sent_at).toLocaleString('zh-CN')
                        : 'UNKNOWN'}
                    </span>
                  </div>
                  <p className="mt-2 text-sm leading-6">
                    {message.text ?? message.placeholder ?? 'UNKNOWN'}
                  </p>
                </li>
              ))}
            </ul>
            <p className="text-xs leading-5 text-muted-foreground">
              详情绑定当前连接 ID：{connection.connection_id.slice(0, 8)}…
              和会话
              ID；当前版本没有发送、自动回复、附件下载、商品/订单、发货、关单或退款入口。模型不接收浏览器会话、Cookie
              或页面控制权。
            </p>
          </div>
        )}
      </CardContent>
    </Card>
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
