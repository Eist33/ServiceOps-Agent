'use client';

// oxlint-disable next/no-html-link-for-pages -- Vinext Docker navigation requires full document requests.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Bot,
  BookOpenText,
  ChartNoAxesCombined,
  Box,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  Clock3,
  Headphones,
  Loader2,
  MessageSquareText,
  PackageCheck,
  ReceiptText,
  RotateCcw,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  TicketCheck,
  Truck,
  UserRoundCheck,
  X,
} from 'lucide-react';

import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import {
  type AgentEvent,
  type ConversationState,
  type OrderData,
  type ShippingData,
  cancelRefund,
  cancelTicketHandoff,
  confirmRefund,
  createConversation,
  createShippingTicket,
  getOrder,
  getShipping,
  handoffTicket,
  loadConversation,
  sendMessage,
} from '@/lib/api';

type ScenarioId = 'policy' | 'shipping' | 'ticket' | 'refund';
type TimelineItem =
  | { id: string; kind: 'message'; role: 'user' | 'agent'; text: string }
  | {
      id: string;
      kind: 'tool';
      name: string;
      status: 'running' | 'succeeded';
      summary?: string;
      duration?: number;
    }
  | {
      id: string;
      kind: 'approval';
      refundId: string;
      amount: string;
      method: string;
      reason: string;
    }
  | { id: string; kind: 'error'; text: string };

const ORDER_NUMBER = 'ORD-20260828-1042';
const STORAGE_KEY = 'harbor-support-conversation';
const scenarios = [
  {
    id: 'policy' as const,
    icon: Search,
    title: '咨询退货政策',
    note: '知识库问答',
    tone: 'text-sky-700 bg-sky-50',
    prompt: '我收到商品后发现不太合适，多少天内可以申请退货？',
  },
  {
    id: 'shipping' as const,
    icon: Truck,
    title: '查询订单物流',
    note: '调用订单工具',
    tone: 'text-indigo-700 bg-indigo-50',
    prompt: `帮我查一下订单 ${ORDER_NUMBER} 到哪里了？已经好几天没更新。`,
  },
  {
    id: 'ticket' as const,
    icon: TicketCheck,
    title: '物流异常建单',
    note: '幂等创建工单',
    tone: 'text-amber-700 bg-amber-50',
    prompt: `物流两天没动了，帮我催一下。订单号是 ${ORDER_NUMBER}。`,
  },
  {
    id: 'refund' as const,
    icon: PackageCheck,
    title: '申请退款',
    note: '需要用户确认',
    tone: 'text-rose-700 bg-rose-50',
    prompt: `订单 ${ORDER_NUMBER} 我不想要了，帮我申请退款。`,
  },
];
const welcome: TimelineItem = {
  id: 'welcome',
  kind: 'message',
  role: 'agent',
  text: '你好，我是售后服务助手。你可以咨询退换货政策，或提供订单号查询物流、创建工单和申请退款。',
};

function displayValue(value: unknown) {
  return typeof value === 'string' || typeof value === 'number'
    ? `${value}`
    : '';
}

function toolSummary(result?: Record<string, unknown>) {
  if (!result) return '业务服务已返回结果';
  if (result.ticket_number)
    return `已创建 ${displayValue(result.ticket_type)} 工单 ${displayValue(result.ticket_number)}`;
  if (result.refund_number)
    return `已创建待确认退款 ${displayValue(result.refund_number)}`;
  if (result.abnormal)
    return `检测到“${displayValue(result.abnormal_reason)}”异常 · 停滞 ${displayValue(result.stale_hours)} 小时`;
  if (result.order_number)
    return `订单归属验证通过 · ${displayValue(result.order_number)}`;
  if (result.confident) {
    const source = (
      result.results as Array<Record<string, unknown>> | undefined
    )?.[0];
    return source
      ? `命中《${displayValue(source.title)}》${displayValue(source.section)} · 相关度 ${Math.round(Number(source.relevance) * 100)}%`
      : '知识检索完成';
  }
  return '业务服务已返回结果';
}

export default function DemoClient() {
  const [activeScenario, setActiveScenario] = useState<ScenarioId>('shipping');
  const [conversationId, setConversationId] = useState('');
  const [items, setItems] = useState<TimelineItem[]>([welcome]);
  const [state, setState] = useState<ConversationState | null>(null);
  const [order, setOrder] = useState<OrderData | null>(null);
  const [shipping, setShipping] = useState<ShippingData | null>(null);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [initializing, setInitializing] = useState(true);
  const [ticketDialogOpen, setTicketDialogOpen] = useState(false);
  const [handoffBusy, setHandoffBusy] = useState(false);
  const [error, setError] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  const refreshState = useCallback(async (id: string) => {
    const next = await loadConversation(id);
    setState(next);
    return next;
  }, []);

  const startFreshConversation = useCallback(async () => {
    const created = await createConversation();
    localStorage.setItem(STORAGE_KEY, created.id);
    setConversationId(created.id);
    setItems([{ ...welcome, id: `welcome-${created.id}` }]);
    setState(null);
    return created.id;
  }, []);

  useEffect(() => {
    async function initialize() {
      try {
        const [orderData, shippingData] = await Promise.all([
          getOrder(),
          getShipping(),
        ]);
        setOrder(orderData);
        setShipping(shippingData);
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
          try {
            const persisted = await loadConversation(saved);
            setConversationId(saved);
            setState(persisted);
            setItems(
              persisted.messages.length
                ? persisted.messages.map((message) => ({
                    id: message.id,
                    kind: 'message' as const,
                    role: message.role,
                    text: message.content,
                  }))
                : [welcome],
            );
          } catch {
            await startFreshConversation();
          }
        } else {
          await startFreshConversation();
        }
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : '初始化失败');
      } finally {
        setInitializing(false);
      }
    }
    void initialize();
  }, [startFreshConversation]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [items, busy]);

  const handleEvent = useCallback((event: AgentEvent) => {
    if (event.type === 'tool_started') {
      setItems((current) => [
        ...current,
        {
          id: event.tool_call_id ?? crypto.randomUUID(),
          kind: 'tool',
          name: String(event.payload.tool_name),
          status: 'running',
        },
      ]);
    } else if (event.type === 'tool_completed') {
      const result = event.payload.result as
        | Record<string, unknown>
        | undefined;
      setItems((current) =>
        current.map((item) =>
          item.kind === 'tool' && item.id === event.tool_call_id
            ? {
                ...item,
                status: 'succeeded',
                duration: Number(event.payload.duration_ms),
                summary: toolSummary(result),
              }
            : item,
        ),
      );
    } else if (event.type === 'approval_required') {
      setItems((current) => [
        ...current,
        {
          id: `approval-${event.refund_request_id}`,
          kind: 'approval',
          refundId: String(event.refund_request_id),
          amount: String(event.payload.amount),
          method: String(event.payload.method),
          reason: String(event.payload.reason),
        },
      ]);
    } else if (event.type === 'message_delta') {
      setItems((current) => [
        ...current,
        {
          id: event.message_id,
          kind: 'message',
          role: 'agent',
          text: String(event.payload.delta),
        },
      ]);
    } else if (event.type === 'error') {
      setItems((current) => [
        ...current,
        {
          id: `error-${event.trace_id}`,
          kind: 'error',
          text: String(event.payload.message),
        },
      ]);
    }
  }, []);

  const runPrompt = useCallback(
    async (id: string, content: string) => {
      setBusy(true);
      setError('');
      setItems((current) => [
        ...current,
        {
          id: `local-${crypto.randomUUID()}`,
          kind: 'message',
          role: 'user',
          text: content,
        },
      ]);
      try {
        await sendMessage(id, content, handleEvent);
        await refreshState(id);
      } catch (caught) {
        setItems((current) => [
          ...current,
          {
            id: `error-${crypto.randomUUID()}`,
            kind: 'error',
            text: caught instanceof Error ? caught.message : '请求失败',
          },
        ]);
      } finally {
        setBusy(false);
      }
    },
    [handleEvent, refreshState],
  );

  async function submit() {
    const value = input.trim();
    if (!value || busy || !conversationId) return;
    setInput('');
    await runPrompt(conversationId, value);
  }

  async function chooseScenario(id: ScenarioId) {
    if (busy) return;
    setActiveScenario(id);
    const scenario = scenarios.find((item) => item.id === id);
    if (!scenario) return;
    try {
      const fresh = await startFreshConversation();
      await runPrompt(fresh, scenario.prompt);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '场景执行失败');
    }
  }

  async function createTicketFromChat() {
    if (!conversationId || busy) return;
    setBusy(true);
    try {
      const ticket = await createShippingTicket(conversationId, ORDER_NUMBER);
      setItems((current) => [
        ...current,
        {
          id: `ticket-${ticket.id}`,
          kind: 'message',
          role: 'agent',
          text: `物流异常工单 ${ticket.ticket_number} 已创建，客服会继续向承运商核实。`,
        },
      ]);
      await refreshState(conversationId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '创建工单失败');
    } finally {
      setBusy(false);
    }
  }

  async function approveRefund(refundId: string) {
    if (busy) return;
    setBusy(true);
    try {
      const refund = await confirmRefund(refundId, crypto.randomUUID());
      setItems((current) => [
        ...current.filter(
          (item) => item.kind !== 'approval' || item.refundId !== refundId,
        ),
        {
          id: `success-${refundId}`,
          kind: 'message',
          role: 'agent',
          text: `退款已模拟完成，¥${refund.amount} 将原路退回。关联工单已更新为已解决。`,
        },
      ]);
      await refreshState(conversationId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '退款确认失败');
    } finally {
      setBusy(false);
    }
  }

  async function rejectRefund(refundId: string) {
    if (busy) return;
    setBusy(true);
    try {
      await cancelRefund(refundId);
      setItems((current) => [
        ...current.filter(
          (item) => item.kind !== 'approval' || item.refundId !== refundId,
        ),
        {
          id: `cancel-${refundId}`,
          kind: 'message',
          role: 'agent',
          text: '本次退款申请已取消，没有执行任何退款操作。',
        },
      ]);
      await refreshState(conversationId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '取消退款失败');
    } finally {
      setBusy(false);
    }
  }

  async function transferTicketToHuman(ticketId: string) {
    if (handoffBusy) return;
    setHandoffBusy(true);
    setError('');
    try {
      const ticket = await handoffTicket(ticketId);
      await refreshState(conversationId);
      setItems((current) => [
        ...current,
        {
          id: `handoff-${ticket.id}`,
          kind: 'message',
          role: 'agent',
          text: `工单 ${ticket.ticket_number} 已转交 ${ticket.assignee_name}，将在 SLA 时限内继续处理。`,
        },
      ]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '转人工失败');
    } finally {
      setHandoffBusy(false);
    }
  }

  async function returnTicketToAgent(ticketId: string) {
    if (handoffBusy) return;
    setHandoffBusy(true);
    setError('');
    try {
      const ticket = await cancelTicketHandoff(ticketId);
      await refreshState(conversationId);
      setItems((current) => [
        ...current,
        {
          id: `handoff-cancel-${ticket.id}`,
          kind: 'message',
          role: 'agent',
          text: `工单 ${ticket.ticket_number} 已撤销人工接管，后续由 Agent 继续处理。`,
        },
      ]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '撤销人工接管失败');
    } finally {
      setHandoffBusy(false);
    }
  }

  const activeTicket = state?.tickets[0] ?? null;
  const activeRefund = state?.refunds[0] ?? null;
  useEffect(() => {
    if (
      !conversationId ||
      activeTicket?.handoff_status !== 'ASSIGNED' ||
      activeTicket.status === 'RESOLVED'
    ) {
      return;
    }
    const intervalId = window.setInterval(() => {
      void refreshState(conversationId).catch(() => {
        // 短暂断线时保留最后一次成功状态，下一轮继续同步。
      });
    }, 5000);
    return () => window.clearInterval(intervalId);
  }, [
    activeTicket?.handoff_status,
    activeTicket?.status,
    conversationId,
    refreshState,
  ]);
  const currentScenario = useMemo(
    () => scenarios.find((item) => item.id === activeScenario) ?? scenarios[1],
    [activeScenario],
  );

  return (
    <main className="min-h-screen bg-background text-foreground">
      <Header />
      <div className="mx-auto grid min-h-[calc(100vh-4rem)] max-w-[1680px] grid-cols-1 lg:grid-cols-[270px_minmax(0,1fr)] xl:grid-cols-[270px_minmax(0,1fr)_330px]">
        <ScenarioNav
          active={activeScenario}
          conversationId={conversationId}
          onChoose={chooseScenario}
        />
        <section className="flex h-[calc(100vh-4rem)] min-w-0 flex-col bg-[#fbfcfc]">
          <div className="flex items-center justify-between border-b border-border/70 bg-white px-4 py-3.5 sm:px-6">
            <div className="flex items-center gap-3">
              <AgentAvatar />
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-sm font-semibold">售后服务助手</h1>
                  <span className="size-1.5 rounded-full bg-emerald-500" />
                </div>
                <p className="text-[11px] text-muted-foreground">
                  {currentScenario.title} · 测试客户 林沐
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {activeTicket && (
                <Button
                  className="xl:hidden"
                  variant="secondary"
                  size="sm"
                  aria-label="查看工单详情"
                  onClick={() => setTicketDialogOpen(true)}
                >
                  <TicketCheck />
                  <span className="hidden sm:inline">工单详情</span>
                </Button>
              )}
              <Button
                variant="outline"
                size="sm"
                disabled={busy}
                onClick={() => void startFreshConversation()}
              >
                <MessageSquareText /> 新对话
              </Button>
            </div>
          </div>
          <div className="flex gap-2 overflow-x-auto border-b bg-white px-4 py-2.5 lg:hidden">
            {scenarios.map((scenario) => (
              <button
                key={scenario.id}
                onClick={() => void chooseScenario(scenario.id)}
                className={`shrink-0 rounded-full border px-3 py-1.5 text-xs ${activeScenario === scenario.id ? 'border-primary bg-primary text-primary-foreground' : 'border-border bg-white'}`}
              >
                {scenario.title}
              </button>
            ))}
          </div>
          <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-7">
            <div className="mx-auto max-w-3xl space-y-4">
              {initializing ? (
                <div className="flex justify-center py-12 text-sm text-muted-foreground">
                  <Loader2 className="mr-2 size-4 animate-spin" />{' '}
                  正在连接业务服务…
                </div>
              ) : (
                items.map((item) => (
                  <TimelineEntry
                    key={item.id}
                    item={item}
                    busy={busy}
                    onConfirm={approveRefund}
                    onCancel={rejectRefund}
                  />
                ))
              )}
              {busy && (
                <div className="flex gap-3">
                  <AgentAvatar />
                  <div className="flex items-center gap-2 rounded-2xl rounded-tl-md border bg-white px-4 py-3 text-xs text-muted-foreground">
                    <Loader2 className="size-3.5 animate-spin" />{' '}
                    正在检查知识与业务数据…
                  </div>
                </div>
              )}
              {activeScenario === 'shipping' &&
                shipping?.abnormal &&
                !activeTicket &&
                !busy && (
                  <div className="ml-11 flex gap-2">
                    <Button
                      size="sm"
                      onClick={() => void createTicketFromChat()}
                    >
                      创建物流工单
                    </Button>
                    <Button size="sm" variant="outline">
                      暂时不用
                    </Button>
                  </div>
                )}
              {error && (
                <p className="text-center text-xs text-destructive">{error}</p>
              )}
              <div ref={bottomRef} />
            </div>
          </div>
          <Composer
            input={input}
            busy={busy || !conversationId}
            onInput={setInput}
            onSubmit={submit}
          />
        </section>
        <ContextPanel
          order={order}
          shipping={shipping}
          ticket={activeTicket}
          refund={activeRefund}
          invocations={state?.tool_invocations ?? []}
          onOpenTicket={() => setTicketDialogOpen(true)}
        />
      </div>
      <TicketDialog
        open={ticketDialogOpen}
        onOpenChange={setTicketDialogOpen}
        ticket={activeTicket}
        busy={handoffBusy}
        onHandoff={transferTicketToHuman}
        onCancelHandoff={returnTicketToAgent}
      />
    </main>
  );
}

function Header() {
  return (
    <header className="flex h-16 items-center justify-between border-b bg-white px-4 lg:px-6">
      <div className="flex items-center gap-3">
        <div className="grid size-9 place-items-center rounded-xl bg-primary text-primary-foreground">
          <Headphones className="size-4.5" />
        </div>
        <div>
          <p className="text-sm font-semibold">Harbor Support</p>
          <p className="text-[11px] text-muted-foreground">
            企业客服 Agent · 运营增强环境
          </p>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <a
          className={buttonVariants({ variant: 'outline', size: 'sm' })}
          href="/operations"
        >
          <ChartNoAxesCombined />
          <span className="hidden sm:inline">运营看板</span>
        </a>
        <a
          className={buttonVariants({ variant: 'outline', size: 'sm' })}
          href="/knowledge"
        >
          <BookOpenText />
          <span className="hidden sm:inline">知识运营</span>
        </a>
        <Badge
          className="hidden bg-emerald-50 text-emerald-700 sm:inline-flex"
          variant="secondary"
        >
          <span className="size-1.5 rounded-full bg-emerald-500" /> API
          与审计已连接
        </Badge>
        <Avatar className="size-8">
          <AvatarFallback className="text-xs font-semibold">林</AvatarFallback>
        </Avatar>
      </div>
    </header>
  );
}

function ScenarioNav({
  active,
  conversationId,
  onChoose,
}: {
  active: ScenarioId;
  conversationId: string;
  onChoose: (id: ScenarioId) => Promise<void>;
}) {
  return (
    <aside className="hidden border-r bg-[#f7f9fa] p-4 lg:block">
      <div className="mb-5 flex items-center justify-between px-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            验收场景
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            点击运行真实业务闭环
          </p>
        </div>
        <Sparkles className="size-4 text-primary" />
      </div>
      <nav className="space-y-2">
        {scenarios.map((scenario) => (
          <button
            className={`group flex w-full items-center gap-3 rounded-xl border p-3 text-left transition ${active === scenario.id ? 'border-primary/20 bg-white shadow-sm' : 'border-transparent hover:bg-white'}`}
            key={scenario.id}
            onClick={() => void onChoose(scenario.id)}
          >
            <span
              className={`grid size-9 place-items-center rounded-lg ${scenario.tone}`}
            >
              <scenario.icon className="size-4" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-medium">
                {scenario.title}
              </span>
              <span className="block text-[11px] text-muted-foreground">
                {scenario.note}
              </span>
            </span>
            <ChevronRight className="size-4 text-muted-foreground/50" />
          </button>
        ))}
      </nav>
      <div className="mt-6 rounded-xl border bg-white p-3 text-xs">
        <p className="font-medium">
          {conversationId ? `CNV-${conversationId.slice(0, 8)}` : '正在连接…'}
        </p>
        <p className="mt-1 text-muted-foreground">
          消息、工具调用和业务对象均持久化
        </p>
      </div>
      <div className="mt-6 rounded-2xl bg-[#eaf1f4] p-4">
        <div className="flex items-center gap-2 text-xs font-semibold text-[#31546a]">
          <ShieldCheck className="size-4" /> 安全边界
        </div>
        <p className="mt-2 text-xs leading-5 text-[#547185]">
          订单归属、异常判定、金额、状态机与幂等均由后端校验。
        </p>
      </div>
    </aside>
  );
}

function AgentAvatar() {
  return (
    <Avatar className="mt-0.5 size-8">
      <AvatarFallback className="bg-primary text-primary-foreground">
        <Bot className="size-3.5" />
      </AvatarFallback>
    </Avatar>
  );
}

function TimelineEntry({
  item,
  busy,
  onConfirm,
  onCancel,
}: {
  item: TimelineItem;
  busy: boolean;
  onConfirm: (id: string) => Promise<void>;
  onCancel: (id: string) => Promise<void>;
}) {
  if (item.kind === 'message' && item.role === 'user')
    return (
      <div className="flex justify-end gap-3">
        <div className="max-w-[78%] rounded-2xl rounded-tr-md bg-primary px-4 py-3 text-sm leading-6 text-primary-foreground">
          {item.text}
        </div>
        <Avatar className="mt-0.5 size-8">
          <AvatarFallback className="text-xs">林</AvatarFallback>
        </Avatar>
      </div>
    );
  if (item.kind === 'message')
    return (
      <div className="flex gap-3">
        <AgentAvatar />
        <div className="max-w-[88%] rounded-2xl rounded-tl-md border bg-white px-4 py-3 text-sm leading-6 shadow-sm">
          {item.text}
        </div>
      </div>
    );
  if (item.kind === 'tool')
    return (
      <div className="ml-11 rounded-xl border border-sky-100 bg-sky-50/70 p-3 text-sky-800">
        <div className="flex items-center gap-2 text-xs font-semibold">
          {item.status === 'running' ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Box className="size-3.5" />
          )}
          {item.status === 'running' ? '正在调用' : '已调用'} {item.name}
        </div>
        <p className="mt-1.5 text-xs opacity-80">
          {item.summary ?? '正在执行服务端校验…'}
          {item.duration ? ` · ${item.duration}ms` : ''}
        </p>
      </div>
    );
  if (item.kind === 'error')
    return (
      <div className="ml-11 flex gap-2 rounded-xl border border-red-100 bg-red-50 p-3 text-xs text-red-700">
        <CircleAlert className="size-4" />
        {item.text}
      </div>
    );
  return (
    <div className="ml-11 overflow-hidden rounded-2xl border border-rose-100 bg-white shadow-sm">
      <div className="border-b border-rose-100 bg-rose-50/70 px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-rose-800">
          <ReceiptText className="size-4" /> 退款确认
        </div>
      </div>
      <div className="grid gap-3 p-4 text-xs sm:grid-cols-3">
        <div>
          <p className="text-muted-foreground">退款金额</p>
          <p className="mt-1 text-base font-semibold">¥{item.amount}</p>
        </div>
        <div>
          <p className="text-muted-foreground">退款方式</p>
          <p className="mt-1 font-medium">{item.method}</p>
        </div>
        <div>
          <p className="text-muted-foreground">退款原因</p>
          <p className="mt-1 font-medium">{item.reason}</p>
        </div>
      </div>
      <div className="flex gap-2 border-t bg-[#fbfcfc] px-4 py-3">
        <Button
          size="sm"
          disabled={busy}
          onClick={() => void onConfirm(item.refundId)}
        >
          <Check /> 确认退款
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => void onCancel(item.refundId)}
        >
          <X /> 取消
        </Button>
      </div>
    </div>
  );
}

function Composer({
  input,
  busy,
  onInput,
  onSubmit,
}: {
  input: string;
  busy: boolean;
  onInput: (value: string) => void;
  onSubmit: () => Promise<void>;
}) {
  return (
    <div className="border-t bg-white px-4 py-4 sm:px-7">
      <div className="mx-auto max-w-3xl">
        <div className="rounded-2xl border bg-white p-2 shadow-[0_8px_28px_rgba(25,55,70,0.08)]">
          <Textarea
            aria-label="输入售后问题"
            className="min-h-16 resize-none border-0 bg-transparent shadow-none focus-visible:ring-0"
            placeholder="描述你的售后问题，或输入订单号……"
            value={input}
            onChange={(event) => onInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                void onSubmit();
              }
            }}
          />
          <div className="flex items-center justify-between px-1 pb-1">
            <span className="text-[11px] text-muted-foreground">
              Enter 发送 · Shift + Enter 换行
            </span>
            <Button
              size="icon"
              aria-label="发送消息"
              disabled={!input.trim() || busy}
              onClick={() => void onSubmit()}
            >
              <Send className="size-4" />
            </Button>
          </div>
        </div>
        <p className="mt-2 text-center text-[10px] text-muted-foreground">
          模拟订单、物流和支付适配器不会产生真实退款
        </p>
      </div>
    </div>
  );
}

function ContextPanel({
  order,
  shipping,
  ticket,
  refund,
  invocations,
  onOpenTicket,
}: {
  order: OrderData | null;
  shipping: ShippingData | null;
  ticket: ConversationState['tickets'][number] | null;
  refund: ConversationState['refunds'][number] | null;
  invocations: ConversationState['tool_invocations'];
  onOpenTicket: () => void;
}) {
  return (
    <aside className="hidden h-[calc(100vh-4rem)] overflow-y-auto border-l bg-white p-5 xl:block">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">业务上下文</h2>
        <Badge variant="outline">服务端数据</Badge>
      </div>
      {order && (
        <div className="mt-5 rounded-2xl border bg-[#fbfcfc] p-4">
          <p className="text-[11px] text-muted-foreground">当前订单</p>
          <p className="mt-1 text-sm font-semibold">{order.order_number}</p>
          <dl className="mt-4 grid grid-cols-2 gap-3 text-xs">
            <div>
              <dt className="text-muted-foreground">商品</dt>
              <dd className="mt-1 font-medium">{order.product_name}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">实付金额</dt>
              <dd className="mt-1 font-medium">¥{order.paid_amount}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">可退金额</dt>
              <dd className="mt-1 font-medium">¥{order.refundable_amount}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">状态</dt>
              <dd className="mt-1 font-medium text-indigo-700">
                {order.status}
              </dd>
            </div>
          </dl>
        </div>
      )}
      {shipping && (
        <div className="mt-4 rounded-2xl border p-4">
          <div className="flex justify-between">
            <p className="text-sm font-semibold">物流轨迹</p>
            <Badge
              className={
                shipping.abnormal
                  ? 'bg-amber-50 text-amber-700'
                  : 'bg-emerald-50 text-emerald-700'
              }
              variant="secondary"
            >
              {shipping.abnormal ? shipping.abnormal_reason : '正常'}
            </Badge>
          </div>
          <div className="mt-4 space-y-4">
            {shipping.nodes.slice(0, 3).map((node) => (
              <div className="flex gap-3" key={node.occurred_at}>
                <span className="mt-1 size-2.5 rounded-full bg-primary" />
                <div>
                  <p className="text-xs font-medium">{node.description}</p>
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    {new Date(node.occurred_at).toLocaleString('zh-CN')}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      {refund && (
        <div className="mt-4 rounded-2xl border border-rose-100 p-4">
          <div className="flex justify-between">
            <p className="text-sm font-semibold">退款申请</p>
            <StatusBadge status={refund.status} />
          </div>
          <p className="mt-3 flex justify-between text-xs">
            <span className="text-muted-foreground">金额</span>
            <span>¥{refund.amount}</span>
          </p>
        </div>
      )}
      <div
        className={`mt-4 rounded-2xl border p-4 ${ticket ? 'border-emerald-100 bg-emerald-50/50' : 'border-dashed bg-[#f7f9fa]'}`}
      >
        <div className="flex justify-between">
          <div className="flex items-center gap-2 text-xs font-semibold">
            <TicketCheck className="size-4" />
            {ticket?.ticket_number ?? '尚未创建工单'}
          </div>
          <StatusBadge status={ticket?.status ?? 'NONE'} />
        </div>
        {ticket && (
          <>
            <dl className="mt-3 grid grid-cols-2 gap-2 border-t border-emerald-100 pt-3 text-[11px]">
              <div>
                <dt className="text-muted-foreground">优先级</dt>
                <dd className="mt-1 font-semibold">{ticket.priority}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">SLA</dt>
                <dd className="mt-1 font-semibold">
                  {slaLabel(ticket.sla_status, ticket.sla_remaining_minutes)}
                </dd>
              </div>
              <div className="col-span-2">
                <dt className="text-muted-foreground">处理队列</dt>
                <dd className="mt-1 font-semibold">
                  {ticket.assignee_name ?? 'Agent 自动处理'}
                </dd>
              </div>
            </dl>
            {ticket.resolution && (
              <div className="mt-3 rounded-xl border border-emerald-200 bg-white p-3">
                <p className="flex items-center gap-1.5 text-[11px] font-semibold text-emerald-800">
                  <CheckCircle2 className="size-3.5" /> 客服处理结果
                </p>
                <p className="mt-2 line-clamp-3 text-xs leading-5 text-foreground">
                  {ticket.resolution.summary}
                </p>
                <p className="mt-2 text-[10px] text-muted-foreground">
                  {ticket.resolution.handled_by} ·{' '}
                  {new Date(ticket.resolution.resolved_at).toLocaleString(
                    'zh-CN',
                  )}
                </p>
              </div>
            )}
            <Button
              className="mt-3 w-full"
              size="sm"
              variant="outline"
              onClick={onOpenTicket}
            >
              查看工单详情
            </Button>
          </>
        )}
      </div>
      <div className="mt-4 rounded-2xl border p-4">
        <div className="flex items-center gap-2 text-xs font-semibold">
          <RotateCcw className="size-4" /> 工具调用审计
        </div>
        <div className="mt-3 space-y-2 text-[11px] text-muted-foreground">
          {invocations.length ? (
            invocations
              .slice(-5)
              .reverse()
              .map((item) => (
                <div className="flex justify-between gap-2" key={item.id}>
                  <span className="truncate">{item.tool_name}</span>
                  <span
                    className={
                      item.status === 'SUCCEEDED'
                        ? 'text-emerald-700'
                        : 'text-red-700'
                    }
                  >
                    {item.status === 'SUCCEEDED' ? '成功' : '失败'} ·{' '}
                    {item.duration_ms}ms
                  </span>
                </div>
              ))
          ) : (
            <p>本会话暂无工具调用</p>
          )}
        </div>
      </div>
    </aside>
  );
}

function StatusBadge({ status }: { status: string }) {
  const labels: Record<string, string> = {
    NONE: '未创建',
    OPEN: '处理中',
    WAITING_APPROVAL: '等待确认',
    RESOLVED: '已解决',
    PENDING_CONFIRMATION: '等待确认',
    PROCESSING: '处理中',
    SUCCEEDED: '已退款',
    CANCELLED: '已取消',
    FAILED: '失败',
  };
  const classes = ['RESOLVED', 'SUCCEEDED'].includes(status)
    ? 'bg-emerald-50 text-emerald-700'
    : ['WAITING_APPROVAL', 'PENDING_CONFIRMATION'].includes(status)
      ? 'bg-rose-50 text-rose-700'
      : ['OPEN', 'PROCESSING'].includes(status)
        ? 'bg-amber-50 text-amber-700'
        : 'bg-muted text-muted-foreground';
  return (
    <span
      className={`rounded-full px-2 py-1 text-[10px] font-semibold ${classes}`}
    >
      {labels[status] ?? status}
    </span>
  );
}

function slaLabel(status: string, remainingMinutes: number) {
  if (status === 'COMPLETED') return '已完成';
  if (status === 'BREACHED') return '已超时';
  const hours = Math.floor(remainingMinutes / 60);
  const minutes = remainingMinutes % 60;
  const remaining = hours ? `${hours} 小时 ${minutes} 分` : `${minutes} 分钟`;
  return status === 'DUE_SOON' ? `即将到期 · ${remaining}` : `正常 · ${remaining}`;
}

function TicketDialog({
  open,
  onOpenChange,
  ticket,
  busy,
  onHandoff,
  onCancelHandoff,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  ticket: ConversationState['tickets'][number] | null;
  busy: boolean;
  onHandoff: (ticketId: string) => Promise<void>;
  onCancelHandoff: (ticketId: string) => Promise<void>;
}) {
  const resolved = ticket?.status === 'RESOLVED';
  const assigned = ticket?.handoff_status === 'ASSIGNED';
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <span
              className={`grid size-10 place-items-center rounded-xl ${resolved ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}
            >
              {resolved ? (
                <CheckCircle2 className="size-5" />
              ) : (
                <Clock3 className="size-5" />
              )}
            </span>
            <div>
              <DialogTitle>{ticket?.ticket_number ?? '工单详情'}</DialogTitle>
              <DialogDescription className="mt-1">
                {ticket?.ticket_type ?? 'SHIPPING'} · 数据库状态
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>
        <div className="rounded-xl border bg-[#fbfcfc] p-4">
          <div className="flex justify-between">
            <span className="text-xs text-muted-foreground">当前状态</span>
            <StatusBadge status={ticket?.status ?? 'NONE'} />
          </div>
          <p className="mt-4 text-xs leading-5">
            {ticket?.reason ?? '暂无工单记录'}
            。状态直接来自数据库，不从对话文本推断。
          </p>
          {ticket && (
            <dl className="mt-4 grid grid-cols-2 gap-3 border-t pt-4 text-xs">
              <div>
                <dt className="text-muted-foreground">优先级</dt>
                <dd className="mt-1 font-semibold">{ticket.priority}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">SLA 状态</dt>
                <dd className="mt-1 font-semibold">
                  {slaLabel(ticket.sla_status, ticket.sla_remaining_minutes)}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">截止时间</dt>
                <dd className="mt-1 font-medium">
                  {new Date(ticket.sla_due_at).toLocaleString('zh-CN')}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">处理队列</dt>
                <dd className="mt-1 font-medium">
                  {ticket.assignee_name ?? '尚未转人工'}
                </dd>
              </div>
            </dl>
          )}
        </div>
        {assigned && (
          <div className="flex items-start gap-3 rounded-xl border border-emerald-100 bg-emerald-50 p-3 text-xs text-emerald-800">
            <UserRoundCheck className="mt-0.5 size-4 shrink-0" />
            <div>
              <p className="font-semibold">人工接管已建立</p>
              <p className="mt-1 leading-5">
                {ticket?.assignee_name} 已接收工单，自动分派记录和 SLA
                截止时间已持久化。
              </p>
            </div>
          </div>
        )}
        {ticket?.resolution && (
          <section className="rounded-xl border border-emerald-100 bg-emerald-50 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-emerald-900">
              <CheckCircle2 className="size-4" /> 客服处理方案
            </div>
            <p className="mt-3 text-sm leading-6 text-emerald-950">
              {ticket.resolution.summary}
            </p>
            <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-emerald-200 pt-3 text-xs">
              <div>
                <dt className="text-emerald-700">处理人</dt>
                <dd className="mt-1 font-semibold">
                  {ticket.resolution.handled_by}
                </dd>
              </div>
              <div>
                <dt className="text-emerald-700">完成时间</dt>
                <dd className="mt-1 font-semibold">
                  {new Date(ticket.resolution.resolved_at).toLocaleString(
                    'zh-CN',
                  )}
                </dd>
              </div>
            </dl>
          </section>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            关闭
          </Button>
          {ticket && !resolved && (
            <Button
              variant={assigned ? 'outline' : 'default'}
              disabled={busy}
              onClick={() =>
                void (assigned
                  ? onCancelHandoff(ticket.id)
                  : onHandoff(ticket.id))
              }
            >
              {busy ? (
                <Loader2 className="animate-spin" />
              ) : assigned ? (
                <RotateCcw />
              ) : (
                <UserRoundCheck />
              )}
              {assigned ? '撤销人工接管' : '转人工处理'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
