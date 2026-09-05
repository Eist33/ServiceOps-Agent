'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  CheckCircle2,
  CircleAlert,
  ClipboardList,
  Clock3,
  Headphones,
  Inbox,
  Loader2,
  MessageSquareText,
  Package,
  RefreshCw,
  Send,
  ShieldCheck,
  TicketCheck,
  UserRoundCheck,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Textarea } from '@/components/ui/textarea';
import { StaffNavigation } from '@/app/staff/staff-navigation';
import {
  type AgentProfileData,
  type AgentTicketData,
  acceptAgentTicket,
  addAgentTicketNote,
  getAgentProfile,
  listAgentTickets,
  resolveAgentTicket,
  sendAgentTicketMessage,
  streamAgentTickets,
} from '@/lib/api';

type QueueFilter = 'ACTIVE' | 'QUEUED' | 'MINE' | 'RESOLVED';
type StreamStatus = 'CONNECTING' | 'LIVE' | 'RECONNECTING';

const filterLabels: Array<{ id: QueueFilter; label: string }> = [
  { id: 'ACTIVE', label: '全部待办' },
  { id: 'QUEUED', label: '待受理' },
  { id: 'MINE', label: '我的处理中' },
  { id: 'RESOLVED', label: '已解决' },
];

export default function AgentWorkbenchClient() {
  const [profile, setProfile] = useState<AgentProfileData | null>(null);
  const [tickets, setTickets] = useState<AgentTicketData[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [filter, setFilter] = useState<QueueFilter>('ACTIVE');
  const [note, setNote] = useState('');
  const [reply, setReply] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [streamStatus, setStreamStatus] = useState<StreamStatus>('CONNECTING');

  async function load() {
    setLoading(true);
    setError('');
    try {
      const [nextProfile, nextTickets] = await Promise.all([
        getAgentProfile(),
        listAgentTickets(),
      ]);
      setProfile(nextProfile);
      setTickets(nextTickets);
      setSelectedId((current) =>
        nextTickets.some((ticket) => ticket.id === current)
          ? current
          : (nextTickets[0]?.id ?? ''),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '坐席工作台加载失败');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    async function initialize() {
      try {
        const [nextProfile, nextTickets] = await Promise.all([
          getAgentProfile(),
          listAgentTickets(),
        ]);
        if (cancelled) return;
        setProfile(nextProfile);
        setTickets(nextTickets);
        setSelectedId(nextTickets[0]?.id ?? '');
      } catch (caught) {
        if (!cancelled) {
          setError(
            caught instanceof Error ? caught.message : '坐席工作台加载失败',
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void initialize();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let stopped = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let controller: AbortController | undefined;

    function scheduleReconnect() {
      if (stopped) return;
      setStreamStatus('RECONNECTING');
      retryTimer = setTimeout(() => void connect(true), 2000);
    }

    async function connect(isRetry = false) {
      if (stopped) return;
      setStreamStatus(isRetry ? 'RECONNECTING' : 'CONNECTING');
      controller = new AbortController();
      try {
        await streamAgentTickets(
          (event) => {
            if (stopped) return;
            setStreamStatus('LIVE');
            if (event.type !== 'ticket_queue_snapshot') return;
            setTickets(event.tickets);
            setSelectedId((current) =>
              event.tickets.some((ticket) => ticket.id === current)
                ? current
                : (event.tickets[0]?.id ?? ''),
            );
            setLoading(false);
          },
          controller.signal,
        );
        scheduleReconnect();
      } catch (caught) {
        if (
          stopped ||
          (caught instanceof DOMException && caught.name === 'AbortError')
        ) {
          return;
        }
        scheduleReconnect();
      }
    }

    void connect();
    return () => {
      stopped = true;
      controller?.abort();
      if (retryTimer) clearTimeout(retryTimer);
    };
  }, []);

  const visibleTickets = useMemo(
    () =>
      tickets.filter((ticket) => {
        if (filter === 'ACTIVE') return ticket.work_state !== 'RESOLVED';
        if (filter === 'MINE') {
          return ticket.work_state === 'IN_PROGRESS' && ticket.is_mine;
        }
        return ticket.work_state === filter;
      }),
    [filter, tickets],
  );
  const selected = tickets.find((ticket) => ticket.id === selectedId) ?? null;
  const queued = tickets.filter((ticket) => ticket.work_state === 'QUEUED').length;
  const inProgress = tickets.filter(
    (ticket) => ticket.work_state === 'IN_PROGRESS' && ticket.is_mine,
  ).length;
  const slaRisk = tickets.filter((ticket) =>
    ['DUE_SOON', 'BREACHED'].includes(ticket.sla_status),
  ).length;

  function updateTicket(ticket: AgentTicketData) {
    setTickets((current) =>
      current
        .map((item) => (item.id === ticket.id ? ticket : item))
        .sort((left, right) => right.updated_at.localeCompare(left.updated_at)),
    );
    setSelectedId(ticket.id);
  }

  async function acceptTicket() {
    if (!selected || busy) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const updated = await acceptAgentTicket(selected.id);
      updateTicket(updated);
      setNotice(`已受理工单 ${updated.ticket_number}`);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : '受理失败';
      try {
        const nextTickets = await listAgentTickets();
        setTickets(nextTickets);
      } catch {
        // 保留原始受理冲突，实时流恢复后会同步最新状态。
      }
      setError(message);
    } finally {
      setBusy(false);
    }
  }

  async function addNote() {
    if (!selected || !note.trim() || busy) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const updated = await addAgentTicketNote(
        selected.id,
        note.trim(),
      );
      updateTicket(updated);
      setNote('');
      setNotice('处理记录已保存');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '保存处理记录失败');
    } finally {
      setBusy(false);
    }
  }

  async function sendReply() {
    if (!selected || !reply.trim() || busy) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const updated = await sendAgentTicketMessage(
        selected.id,
        reply.trim(),
      );
      updateTicket(updated);
      setReply('');
      setNotice('回复已发送给客户');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '回复客户失败');
    } finally {
      setBusy(false);
    }
  }

  async function resolveTicket() {
    if (!selected || !note.trim() || busy) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const updated = await resolveAgentTicket(
        selected.id,
        note.trim(),
      );
      updateTicket(updated);
      setNote('');
      setNotice(`工单 ${updated.ticket_number} 已解决`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '解决工单失败');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#f4f6f7] text-foreground">
      <header className="border-b bg-white">
        <div className="mx-auto flex min-h-16 max-w-[1600px] flex-wrap items-center justify-between gap-3 px-4 py-3 lg:px-8">
          <div className="flex items-center gap-3">
            <span className="grid size-9 place-items-center rounded-xl bg-primary text-primary-foreground">
              <Headphones className="size-4.5" />
            </span>
            <div>
              <p className="text-sm font-semibold">Harbor Desk</p>
              <p className="text-[11px] text-muted-foreground">人工坐席处理工作台</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <StaffNavigation active="agent" />
            <RealtimeStatusBadge status={streamStatus} />
            <span className="sr-only">当前坐席：{profile?.name ?? '校验中'}</span>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-[1600px] space-y-5 px-4 py-6 lg:px-8">
        <section className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
          <div>
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-primary">
              <ShieldCheck className="size-4" /> 服务端工单事实
            </div>
            <h1 className="text-2xl font-semibold tracking-tight">人工工单队列</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              新工单会实时进入队列；受理后可记录处理进展并完成解决闭环。
            </p>
          </div>
          <Button variant="outline" onClick={() => void load()} disabled={loading || busy}>
            <RefreshCw className={loading ? 'animate-spin' : ''} /> 刷新队列
          </Button>
        </section>

        {(error || notice) && (
          <div
            className={`flex items-center gap-2 rounded-xl border px-4 py-3 text-sm ${
              error
                ? 'border-red-100 bg-red-50 text-red-700'
                : 'border-emerald-100 bg-emerald-50 text-emerald-700'
            }`}
            role={error ? 'alert' : 'status'}
          >
            {error ? <CircleAlert className="size-4" /> : <CheckCircle2 className="size-4" />}
            {error || notice}
          </div>
        )}

        <section className="grid gap-3 sm:grid-cols-3">
          <QueueMetric label="待受理" value={queued} icon={Inbox} tone="bg-amber-50 text-amber-700" />
          <QueueMetric label="我的处理中" value={inProgress} icon={UserRoundCheck} tone="bg-sky-50 text-sky-700" />
          <QueueMetric label="SLA 风险" value={slaRisk} icon={Clock3} tone="bg-rose-50 text-rose-700" />
        </section>

        <section className="grid min-h-[640px] gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
          <Card className="min-h-0">
            <CardHeader className="border-b">
              <CardTitle>工单队列</CardTitle>
              <CardDescription>优先处理即将超时与尚未受理的工单</CardDescription>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {filterLabels.map((item) => (
                  <Button
                    key={item.id}
                    size="xs"
                    variant={filter === item.id ? 'default' : 'outline'}
                    aria-pressed={filter === item.id}
                    onClick={() => setFilter(item.id)}
                  >
                    {item.label}
                  </Button>
                ))}
              </div>
            </CardHeader>
            <CardContent className="min-h-0 px-2">
              {loading ? (
                <div className="flex justify-center py-20 text-sm text-muted-foreground">
                  <Loader2 className="mr-2 size-4 animate-spin" /> 正在读取工单队列…
                </div>
              ) : visibleTickets.length ? (
                <ScrollArea className="h-[520px] pr-2">
                  <div className="space-y-2 py-1">
                    {visibleTickets.map((ticket) => (
                      <TicketQueueItem
                        key={ticket.id}
                        ticket={ticket}
                        active={ticket.id === selectedId}
                        onSelect={() => {
                          setSelectedId(ticket.id);
                          setNote('');
                          setReply('');
                          setNotice('');
                        }}
                      />
                    ))}
                  </div>
                </ScrollArea>
              ) : (
                <div className="flex flex-col items-center px-5 py-20 text-center text-sm text-muted-foreground">
                  <Inbox className="mb-3 size-7 opacity-50" />
                  当前筛选下没有工单。客户转人工后会自动进入这里。
                </div>
              )}
            </CardContent>
          </Card>

          {selected ? (
            <TicketWorkspace
              ticket={selected}
              note={note}
              reply={reply}
              busy={busy}
              onNoteChange={setNote}
              onReplyChange={setReply}
              onAccept={acceptTicket}
              onAddNote={addNote}
              onSendReply={sendReply}
              onResolve={resolveTicket}
            />
          ) : (
            <Card className="grid place-items-center">
              <div className="max-w-sm px-6 text-center text-muted-foreground">
                <ClipboardList className="mx-auto mb-4 size-9 opacity-40" />
                <p className="font-medium text-foreground">选择一张工单开始处理</p>
                <p className="mt-2 text-sm leading-6">
                  如果队列为空，请先在客户工作台创建物流异常工单并转人工。
                </p>
              </div>
            </Card>
          )}
        </section>
      </div>
    </main>
  );
}

function RealtimeStatusBadge({ status }: { status: StreamStatus }) {
  const config = {
    CONNECTING: ['实时连接中', 'bg-amber-50 text-amber-700', 'bg-amber-500'],
    LIVE: ['实时已连接', 'bg-emerald-50 text-emerald-700', 'bg-emerald-500'],
    RECONNECTING: ['自动重连中', 'bg-rose-50 text-rose-700', 'bg-rose-500'],
  }[status];

  return (
    <Badge
      aria-label="实时队列状态"
      variant="secondary"
      className={config[1]}
    >
      <span className={`size-1.5 rounded-full ${config[2]}`} /> {config[0]}
    </Badge>
  );
}

function QueueMetric({
  label,
  value,
  icon: Icon,
  tone,
}: {
  label: string;
  value: number;
  icon: typeof Inbox;
  tone: string;
}) {
  return (
    <Card size="sm" aria-label={label}>
      <CardContent className="flex items-center justify-between">
        <div>
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
        </div>
        <span className={`grid size-9 place-items-center rounded-xl ${tone}`}>
          <Icon className="size-4.5" />
        </span>
      </CardContent>
    </Card>
  );
}

function TicketQueueItem({
  ticket,
  active,
  onSelect,
}: {
  ticket: AgentTicketData;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      className={`w-full rounded-xl border p-3 text-left transition-colors ${
        active ? 'border-primary/30 bg-primary/5' : 'bg-white hover:bg-muted/50'
      }`}
      aria-label={`打开工单 ${ticket.ticket_number}`}
      onClick={onSelect}
      type="button"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs font-semibold">{ticket.ticket_number}</p>
          <p className="mt-1 text-[11px] text-muted-foreground">
            {ticket.customer_name} · {ticket.order_number}
          </p>
        </div>
        <WorkStateBadge state={ticket.work_state} />
      </div>
      <p className="mt-3 line-clamp-2 text-xs leading-5">{ticket.reason}</p>
      <div className="mt-3 flex items-center justify-between text-[11px] text-muted-foreground">
        <span>{ticket.priority} · {ticket.support_group}</span>
        <span>{slaLabel(ticket)}</span>
      </div>
      {ticket.work_state === 'IN_PROGRESS' && (
        <p className="mt-2 text-[11px] font-medium text-sky-700">
          {ticket.is_mine ? '由我处理' : `由 ${ticket.assignee_name} 处理`}
        </p>
      )}
    </button>
  );
}

function TicketWorkspace({
  ticket,
  note,
  reply,
  busy,
  onNoteChange,
  onReplyChange,
  onAccept,
  onAddNote,
  onSendReply,
  onResolve,
}: {
  ticket: AgentTicketData;
  note: string;
  reply: string;
  busy: boolean;
  onNoteChange: (value: string) => void;
  onReplyChange: (value: string) => void;
  onAccept: () => Promise<void>;
  onAddNote: () => Promise<void>;
  onSendReply: () => Promise<void>;
  onResolve: () => Promise<void>;
}) {
  return (
    <div className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
      <Card>
        <CardHeader className="border-b">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <TicketCheck className="size-4 text-primary" />
                <CardTitle>{ticket.ticket_number}</CardTitle>
                <Badge variant="outline">{ticket.priority}</Badge>
              </div>
              <CardDescription className="mt-2">
                {ticket.customer_name} · {ticket.order_number} · {ticket.product_name}
              </CardDescription>
            </div>
            <WorkStateBadge state={ticket.work_state} />
          </div>
        </CardHeader>
        <CardContent className="space-y-5">
          <section className="rounded-xl border bg-[#fbfcfc] p-4">
            <div className="flex items-center gap-2 text-xs font-semibold">
              <Package className="size-4 text-primary" /> 客户诉求
            </div>
            <p className="mt-3 text-sm leading-6">{ticket.reason}</p>
            <dl className="mt-4 grid gap-3 border-t pt-4 text-xs sm:grid-cols-3">
              <Info label="处理队列" value={ticket.support_group} />
              <Info label="当前负责人" value={ticket.assignee_name ?? '待分派'} />
              <Info label="SLA" value={slaLabel(ticket)} />
            </dl>
          </section>

          <section className="rounded-xl border p-4">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <MessageSquareText className="size-4 text-primary" /> 客户沟通
            </div>
            <div className="mt-3 space-y-2" aria-label="工单沟通记录">
              {ticket.messages.length ? (
                ticket.messages.map((item) => (
                  <div
                    key={item.id}
                    className={`max-w-[88%] rounded-xl px-3 py-2 text-xs leading-5 ${
                      item.sender_role === 'SUPPORT_AGENT'
                        ? 'ml-auto bg-primary text-primary-foreground'
                        : 'border bg-muted/40'
                    }`}
                  >
                    <p className="mb-1 text-[10px] opacity-70">
                      {item.sender_name} ·{' '}
                      {new Date(item.created_at).toLocaleTimeString('zh-CN', {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </p>
                    <p>{item.content}</p>
                  </div>
                ))
              ) : (
                <p className="py-3 text-center text-xs text-muted-foreground">
                  暂无客户补充消息。
                </p>
              )}
            </div>
            {ticket.work_state === 'IN_PROGRESS' && ticket.is_mine && (
              <div className="mt-3 border-t pt-3">
                <Textarea
                  aria-label="回复客户"
                  value={reply}
                  onChange={(event) => onReplyChange(event.target.value)}
                  placeholder="向客户同步核查进展或处理方案……"
                  maxLength={500}
                />
                <Button
                  className="mt-2"
                  variant="outline"
                  disabled={busy || !reply.trim()}
                  onClick={() => void onSendReply()}
                >
                  {busy ? <Loader2 className="animate-spin" /> : <Send />}
                  发送给客户
                </Button>
              </div>
            )}
          </section>

          {ticket.work_state === 'QUEUED' ? (
            <section className="rounded-xl border border-amber-100 bg-amber-50 p-4">
              <p className="text-sm font-semibold text-amber-900">等待坐席受理</p>
              <p className="mt-1 text-xs leading-5 text-amber-800">
                受理后才可以添加处理记录或解决工单，所有操作都会进入审计时间线。
              </p>
              <Button className="mt-4" onClick={() => void onAccept()} disabled={busy}>
                {busy ? <Loader2 className="animate-spin" /> : <UserRoundCheck />}
                受理此工单
              </Button>
            </section>
          ) : ticket.work_state === 'IN_PROGRESS' && ticket.is_mine ? (
            <section className="space-y-3 rounded-xl border p-4">
              <div>
                <p className="text-sm font-semibold">处理记录与解决说明</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  添加记录会继续保持处理中；标记解决会完成工单与人工接管。
                </p>
              </div>
              <Textarea
                aria-label="处理记录或解决说明"
                value={note}
                onChange={(event) => onNoteChange(event.target.value)}
                placeholder="例如：已联系承运商，确认今晚恢复转运……"
                maxLength={500}
              />
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  disabled={busy || !note.trim()}
                  onClick={() => void onAddNote()}
                >
                  {busy ? <Loader2 className="animate-spin" /> : <MessageSquareText />}
                  添加处理记录
                </Button>
                <Button
                  disabled={busy || !note.trim()}
                  onClick={() => void onResolve()}
                >
                  {busy ? <Loader2 className="animate-spin" /> : <CheckCircle2 />}
                  标记已解决
                </Button>
              </div>
            </section>
          ) : ticket.work_state === 'IN_PROGRESS' ? (
            <section className="flex items-start gap-3 rounded-xl border border-sky-100 bg-sky-50 p-4 text-sky-800">
              <ShieldCheck className="mt-0.5 size-5 shrink-0" />
              <div>
                <p className="text-sm font-semibold">
                  已由 {ticket.assignee_name} 受理
                </p>
                <p className="mt-1 text-xs leading-5">
                  当前坐席可以查看处理进度，但不能添加记录或解决其他坐席的工单。
                </p>
              </div>
            </section>
          ) : (
            <section className="flex items-start gap-3 rounded-xl border border-emerald-100 bg-emerald-50 p-4 text-emerald-800">
              <CheckCircle2 className="mt-0.5 size-5 shrink-0" />
              <div>
                <p className="text-sm font-semibold">工单已完成</p>
                <p className="mt-1 text-xs leading-5">
                  解决说明和操作人已记录在坐席时间线中；客户侧当前仅同步已解决状态。
                </p>
              </div>
            </section>
          )}
        </CardContent>
      </Card>

      <Card className="min-h-0">
        <CardHeader className="border-b">
          <CardTitle>处理时间线</CardTitle>
          <CardDescription>来自服务端的完整审计事件</CardDescription>
        </CardHeader>
        <CardContent className="min-h-0 px-3">
          <ScrollArea className="h-[530px] pr-3">
            <div className="space-y-0 py-1">
              {ticket.events.map((event, index) => (
                <div className="relative flex gap-3 pb-5" key={`${event.action}-${event.created_at}`}>
                  {index < ticket.events.length - 1 && (
                    <span className="absolute left-[7px] top-4 h-full w-px bg-border" />
                  )}
                  <span className="relative mt-1.5 size-3.5 shrink-0 rounded-full border-2 border-white bg-primary ring-1 ring-primary/25" />
                  <div className="min-w-0">
                    <p className="text-xs font-semibold">{eventLabel(event.action)}</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      {event.detail}
                    </p>
                    <p className="mt-1.5 text-[10px] text-muted-foreground">
                      {event.actor} · {new Date(event.created_at).toLocaleString('zh-CN')}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="mt-1 font-semibold">{value}</dd>
    </div>
  );
}

function WorkStateBadge({ state }: { state: AgentTicketData['work_state'] }) {
  const config = {
    QUEUED: ['待受理', 'bg-amber-50 text-amber-700'],
    IN_PROGRESS: ['处理中', 'bg-sky-50 text-sky-700'],
    RESOLVED: ['已解决', 'bg-emerald-50 text-emerald-700'],
  }[state];
  return (
    <Badge variant="secondary" className={config[1]}>
      {config[0]}
    </Badge>
  );
}

function slaLabel(ticket: AgentTicketData) {
  if (ticket.sla_status === 'COMPLETED') return '已完成';
  if (ticket.sla_status === 'BREACHED') return '已超时';
  const hours = Math.floor(ticket.sla_remaining_minutes / 60);
  const minutes = ticket.sla_remaining_minutes % 60;
  const remaining = hours ? `${hours}小时${minutes}分` : `${minutes}分钟`;
  return ticket.sla_status === 'DUE_SOON' ? `即将到期 · ${remaining}` : `剩余 ${remaining}`;
}

function eventLabel(action: string) {
  const labels: Record<string, string> = {
    CREATED: '工单创建',
    HUMAN_HANDOFF_ASSIGNED: '进入人工队列',
    HUMAN_HANDOFF_ACCEPTED: '坐席受理',
    HUMAN_HANDOFF_CANCELLED: '撤销人工接管',
    AGENT_NOTE_ADDED: '新增处理记录',
    CUSTOMER_MESSAGE_SENT: '客户发送消息',
    AGENT_REPLY_SENT: '坐席回复客户',
    STATUS_RESOLVED: '工单解决',
  };
  return labels[action] ?? action;
}
