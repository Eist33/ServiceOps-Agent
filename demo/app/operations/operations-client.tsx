'use client';

// oxlint-disable next/no-html-link-for-pages -- Vinext Docker navigation requires full document requests.

import { useEffect, useState } from 'react';
import {
  Activity,
  ArrowLeft,
  BellRing,
  BookOpenText,
  Bot,
  ChartNoAxesCombined,
  CheckCircle2,
  CircleAlert,
  ClipboardCheck,
  Clock3,
  Download,
  Headphones,
  Loader2,
  ReceiptText,
  Star,
  TicketCheck,
  TriangleAlert,
  UserRoundCheck,
} from 'lucide-react';
import { Bar, BarChart, CartesianGrid, XAxis } from 'recharts';

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
  type ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from '@/components/ui/chart';
import { Progress, ProgressLabel } from '@/components/ui/progress';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  type OperationsDashboardData,
  type OperationsAlertSnapshotData,
  type OperationsQualityReportData,
  type OperationsTicketReportData,
  acknowledgeOperationsAlert,
  getOperationsDashboard,
  getOperationsQualityReport,
  getOperationsTicketReport,
  streamOperationsAlerts,
} from '@/lib/api';

const activityConfig = {
  tickets: { label: '新工单', color: 'oklch(0.52 0.09 220)' },
  refunds: { label: '退款申请', color: 'oklch(0.66 0.14 25)' },
  tools: { label: '工具调用', color: 'oklch(0.7 0.12 150)' },
} satisfies ChartConfig;

export default function OperationsClient() {
  const [dashboard, setDashboard] = useState<OperationsDashboardData | null>(null);
  const [alertSnapshot, setAlertSnapshot] =
    useState<OperationsAlertSnapshotData | null>(null);
  const [alertConnection, setAlertConnection] =
    useState<'CONNECTING' | 'LIVE' | 'RECONNECTING'>('CONNECTING');
  const [alertRevision, setAlertRevision] = useState(0);
  const [acknowledgingAlertId, setAcknowledgingAlertId] = useState<string | null>(null);
  const [acknowledgementError, setAcknowledgementError] = useState('');
  const [ticketReport, setTicketReport] =
    useState<OperationsTicketReportData | null>(null);
  const [qualityReport, setQualityReport] =
    useState<OperationsQualityReportData | null>(null);
  const [qualityLoading, setQualityLoading] = useState(true);
  const [qualityError, setQualityError] = useState('');
  const [supportGroup, setSupportGroup] = useState('ALL');
  const [slaStatus, setSlaStatus] = useState('ALL');
  const [reportLoading, setReportLoading] = useState(true);
  const [reportError, setReportError] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    async function initialize() {
      try {
        const data = await getOperationsDashboard();
        if (!cancelled) setDashboard(data);
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : '运营数据加载失败');
        }
      }
    }
    void initialize();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function loadQualityReport() {
      setQualityLoading(true);
      setQualityError('');
      try {
        const data = await getOperationsQualityReport();
        if (!cancelled) setQualityReport(data);
      } catch (caught) {
        if (!cancelled) {
          setQualityError(
            caught instanceof Error ? caught.message : '工单质检数据加载失败',
          );
        }
      } finally {
        if (!cancelled) setQualityLoading(false);
      }
    }
    void loadQualityReport();
    return () => {
      cancelled = true;
    };
  }, []);

  async function acknowledgeAlert(
    alert: OperationsAlertSnapshotData['items'][number],
  ) {
    setAcknowledgingAlertId(alert.id);
    setAcknowledgementError('');
    try {
      const acknowledgement = await acknowledgeOperationsAlert(
        alert.ticket_id,
        alert.type,
      );
      setAlertSnapshot((current) => {
        if (!current) return current;
        const target = current.items.find((item) => item.id === alert.id);
        const newlyAcknowledged = target && !target.acknowledged ? 1 : 0;
        return {
          ...current,
          unacknowledged: Math.max(0, current.unacknowledged - newlyAcknowledged),
          items: current.items.map((item) =>
            item.id === alert.id
              ? {
                  ...item,
                  acknowledged: true,
                  acknowledged_by: acknowledgement.acknowledged_by,
                  acknowledged_at: acknowledgement.acknowledged_at,
                }
              : item,
          ),
        };
      });
    } catch (caught) {
      setAcknowledgementError(
        caught instanceof Error ? caught.message : '告警确认失败，请重试',
      );
    } finally {
      setAcknowledgingAlertId(null);
    }
  }

  useEffect(() => {
    let cancelled = false;
    async function loadTicketReport() {
      setReportLoading(true);
      setReportError('');
      try {
        const data = await getOperationsTicketReport({
          supportGroup: supportGroup === 'ALL' ? undefined : supportGroup,
          slaStatus: slaStatus === 'ALL' ? undefined : slaStatus,
        });
        if (!cancelled) setTicketReport(data);
      } catch (caught) {
        if (!cancelled) {
          setReportError(
            caught instanceof Error ? caught.message : '工单报表加载失败',
          );
        }
      } finally {
        if (!cancelled) setReportLoading(false);
      }
    }
    void loadTicketReport();
    return () => {
      cancelled = true;
    };
  }, [alertRevision, slaStatus, supportGroup]);

  useEffect(() => {
    let disposed = false;
    let controller: AbortController | null = null;
    let retryTimer: number | undefined;

    async function connect() {
      if (disposed) return;
      controller = new AbortController();
      try {
        await streamOperationsAlerts(
          (event) => {
            if (disposed) return;
            setAlertConnection('LIVE');
            if (event.type === 'operations_alert_snapshot') {
              setAlertSnapshot(event.snapshot);
              setAlertRevision((revision) => revision + 1);
              void getOperationsDashboard().then(
                (data) => {
                  if (!disposed) setDashboard(data);
                },
                () => undefined,
              );
            }
          },
          controller.signal,
        );
      } catch (caught) {
        if (caught instanceof DOMException && caught.name === 'AbortError') return;
      }
      if (!disposed) {
        setAlertConnection('RECONNECTING');
        retryTimer = window.setTimeout(() => void connect(), 1500);
      }
    }

    void connect();
    return () => {
      disposed = true;
      controller?.abort();
      if (retryTimer) window.clearTimeout(retryTimer);
    };
  }, []);

  return (
    <main className="min-h-screen bg-[#f5f8f9] text-foreground">
      <header className="border-b bg-white">
        <div className="mx-auto flex min-h-16 max-w-[1500px] flex-wrap items-center justify-between gap-3 px-4 py-3 lg:px-8">
          <div className="flex items-center gap-3">
            <span className="grid size-9 place-items-center rounded-xl bg-primary text-primary-foreground">
              <ChartNoAxesCombined className="size-4.5" />
            </span>
            <div>
              <p className="text-sm font-semibold">Harbor Operations</p>
              <p className="text-[11px] text-muted-foreground">客服质量与执行看板</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <a
              className={buttonVariants({ variant: 'outline', size: 'sm' })}
              href="/knowledge"
            >
              <BookOpenText /> 知识运营
            </a>
            <a className={buttonVariants({ variant: 'outline', size: 'sm' })} href="/">
              <ArrowLeft /> 客服工作台
            </a>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-[1500px] space-y-6 px-4 py-7 lg:px-8">
        <section className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
          <div>
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-primary">
              <Activity className="size-4" /> 实时业务事实
            </div>
            <h1 className="text-2xl font-semibold tracking-tight">运营质量总览</h1>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              聚合工单、SLA、人工接管、退款和工具审计，所有指标均来自服务端数据库。
            </p>
          </div>
          {dashboard && (
            <p className="text-xs text-muted-foreground">
              更新时间 {new Date(dashboard.generated_at).toLocaleString('zh-CN')}
            </p>
          )}
        </section>

        {error && (
          <div className="flex items-center gap-2 rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700" role="alert">
            <CircleAlert className="size-4" /> {error}
          </div>
        )}

        {!dashboard && !error ? (
          <div className="flex justify-center rounded-2xl border bg-white py-24 text-sm text-muted-foreground">
            <Loader2 className="mr-2 size-4 animate-spin" /> 正在汇总运营数据…
          </div>
        ) : dashboard ? (
          <>
            <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                label="活动工单"
                value={dashboard.tickets.active}
                note={`${dashboard.tickets.resolved} 张已解决`}
                icon={TicketCheck}
                tone="bg-sky-50 text-sky-700"
              />
              <MetricCard
                label="人工接管"
                value={dashboard.tickets.assigned}
                note={`${dashboard.tickets.total} 张累计工单`}
                icon={UserRoundCheck}
                tone="bg-violet-50 text-violet-700"
              />
              <MetricCard
                label="SLA 风险"
                value={dashboard.tickets.due_soon + dashboard.tickets.breached}
                note={`${dashboard.tickets.breached} 张已超时`}
                icon={Clock3}
                tone="bg-amber-50 text-amber-700"
              />
              <MetricCard
                label="已完成退款"
                value={dashboard.refunds.succeeded}
                note={`累计 ¥${dashboard.refunds.total_refunded_amount}`}
                icon={ReceiptText}
                tone="bg-emerald-50 text-emerald-700"
              />
            </section>

            <Card aria-label="主动告警中心" className="overflow-hidden">
              <CardHeader className="border-b bg-[linear-gradient(115deg,#fff7ed_0%,#ffffff_46%,#f0f9ff_100%)]">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <CardTitle className="flex items-center gap-2">
                      <BellRing className="size-5 text-amber-600" /> 主动告警中心
                    </CardTitle>
                    <CardDescription className="mt-1">
                      自动推送待受理人工工单与 SLA 风险，无需刷新页面
                    </CardDescription>
                  </div>
                  <AlertConnectionBadge status={alertConnection} />
                </div>
                {alertSnapshot && (
                  <div className="mt-3 flex flex-wrap gap-2 text-xs">
                    <Badge className="bg-violet-50 text-violet-700" variant="secondary">
                      待确认 {alertSnapshot.unacknowledged}
                    </Badge>
                    <Badge className="bg-red-50 text-red-700" variant="secondary">
                      紧急 {alertSnapshot.critical}
                    </Badge>
                    <Badge className="bg-amber-50 text-amber-700" variant="secondary">
                      高优先 {alertSnapshot.high}
                    </Badge>
                    <Badge className="bg-sky-50 text-sky-700" variant="secondary">
                      待受理 {alertSnapshot.medium}
                    </Badge>
                  </div>
                )}
              </CardHeader>
              <CardContent className="pt-5">
                {acknowledgementError && (
                  <div className="mb-4 flex items-center gap-2 rounded-xl border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-700" role="alert">
                    <CircleAlert className="size-4" /> {acknowledgementError}
                  </div>
                )}
                {!alertSnapshot ? (
                  <div className="flex justify-center py-8 text-sm text-muted-foreground">
                    <Loader2 className="mr-2 size-4 animate-spin" /> 正在建立实时告警连接…
                  </div>
                ) : alertSnapshot.items.length ? (
                  <div className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
                    {alertSnapshot.items.map((alert) => (
                      <AlertCard
                        alert={alert}
                        acknowledging={acknowledgingAlertId === alert.id}
                        key={alert.id}
                        onAcknowledge={() => void acknowledgeAlert(alert)}
                      />
                    ))}
                  </div>
                ) : (
                  <EmptyState icon={BellRing} text="当前没有需要运营介入的主动告警。" />
                )}
              </CardContent>
            </Card>

            <section className="grid gap-6 xl:grid-cols-[minmax(0,1.7fr)_minmax(300px,0.8fr)]">
              <Card>
                <CardHeader>
                  <CardTitle>近 7 天业务活动</CardTitle>
                  <CardDescription>新工单、退款申请和 Agent 工具调用趋势</CardDescription>
                </CardHeader>
                <CardContent>
                  <ChartContainer config={activityConfig} className="h-[290px] w-full aspect-auto">
                    <BarChart accessibilityLayer data={dashboard.activity}>
                      <CartesianGrid vertical={false} />
                      <XAxis dataKey="label" tickLine={false} axisLine={false} />
                      <ChartTooltip content={<ChartTooltipContent />} />
                      <Bar dataKey="tickets" fill="var(--color-tickets)" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="refunds" fill="var(--color-refunds)" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="tools" fill="var(--color-tools)" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ChartContainer>
                  <div className="mt-3 flex flex-wrap gap-4 text-xs text-muted-foreground">
                    <LegendDot color="bg-[#457188]" label="新工单" />
                    <LegendDot color="bg-[#c77063]" label="退款申请" />
                    <LegendDot color="bg-[#55a278]" label="工具调用" />
                  </div>
                </CardContent>
              </Card>

              <div className="grid gap-6">
                <Card>
                  <CardHeader>
                    <CardTitle>Agent 工具健康度</CardTitle>
                    <CardDescription>结构化工具调用执行质量</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="flex items-end justify-between">
                      <div>
                        <p className="text-3xl font-semibold tabular-nums">
                          {dashboard.tools.total ? `${dashboard.tools.success_rate}%` : '—'}
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">成功率</p>
                      </div>
                      <Badge variant="secondary" className="bg-emerald-50 text-emerald-700">
                        {dashboard.tools.failed} 次失败
                      </Badge>
                    </div>
                    <Progress value={dashboard.tools.success_rate}>
                      <ProgressLabel>成功调用</ProgressLabel>
                      <span className="ml-auto text-sm tabular-nums text-muted-foreground">
                        {dashboard.tools.succeeded} / {dashboard.tools.total}
                      </span>
                    </Progress>
                    <div className="rounded-xl border bg-[#fbfcfc] p-3 text-xs">
                      <span className="text-muted-foreground">平均耗时</span>
                      <span className="float-right font-semibold tabular-nums">
                        {dashboard.tools.average_duration_ms} ms
                      </span>
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>知识库状态</CardTitle>
                    <CardDescription>当前客服检索可用范围</CardDescription>
                  </CardHeader>
                  <CardContent className="grid grid-cols-3 gap-2 text-center">
                    <MiniMetric label="生效" value={dashboard.knowledge.active} />
                    <MiniMetric label="历史" value={dashboard.knowledge.historical} />
                    <MiniMetric label="版本" value={dashboard.knowledge.versions} />
                  </CardContent>
                </Card>
              </div>
            </section>

            <Card>
              <CardHeader>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <CardTitle className="flex items-center gap-2">
                      <ClipboardCheck className="size-4 text-primary" /> 人工工单自动质检
                    </CardTitle>
                    <CardDescription className="mt-1">
                      按 SLA、首次回复、内部记录与解决方案完整度自动评分
                    </CardDescription>
                  </div>
                  {qualityReport && (
                    <div className="flex flex-wrap gap-2 text-xs">
                      <Badge variant="secondary">已质检 {qualityReport.total}</Badge>
                      <Badge className="bg-emerald-50 text-emerald-700" variant="secondary">
                        平均 {qualityReport.average_score} 分
                      </Badge>
                      <Badge className="bg-amber-50 text-amber-700" variant="secondary">
                        待改进 {qualityReport.attention}
                      </Badge>
                      <Badge className="bg-sky-50 text-sky-700" variant="secondary">
                        客户评价 {qualityReport.feedback_received} · 均分{' '}
                        {qualityReport.average_customer_rating.toFixed(1)}
                      </Badge>
                      <Badge className="bg-rose-50 text-rose-700" variant="secondary">
                        低分 {qualityReport.low_ratings}
                      </Badge>
                    </div>
                  )}
                </div>
              </CardHeader>
              <CardContent className="px-0">
                {qualityLoading ? (
                  <div className="flex justify-center py-10 text-sm text-muted-foreground">
                    <Loader2 className="mr-2 size-4 animate-spin" /> 正在生成质检结果…
                  </div>
                ) : qualityError ? (
                  <EmptyState icon={CircleAlert} text={qualityError} />
                ) : qualityReport?.items.length ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="pl-4">工单</TableHead>
                        <TableHead>处理坐席</TableHead>
                        <TableHead>得分</TableHead>
                        <TableHead>结果</TableHead>
                        <TableHead>客户评价</TableHead>
                        <TableHead>检查项</TableHead>
                        <TableHead className="pr-4">解决时间</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {qualityReport.items.map((item) => {
                        const failedChecks = item.checks.filter((check) => !check.passed);
                        return (
                          <TableRow key={item.ticket_id}>
                            <TableCell className="pl-4">
                              <p className="font-medium">{item.ticket_number}</p>
                              <p className="mt-1 text-[11px] text-muted-foreground">
                                {item.customer_name} · {item.order_number}
                              </p>
                            </TableCell>
                            <TableCell>
                              <p>{item.assignee_name}</p>
                              <p className="mt-1 text-[11px] text-muted-foreground">
                                {item.support_group}
                              </p>
                            </TableCell>
                            <TableCell className="font-semibold tabular-nums">
                              {item.score} 分
                            </TableCell>
                            <TableCell><QualityBadge grade={item.grade} /></TableCell>
                            <TableCell>
                              {item.customer_rating ? (
                                <div className="max-w-44">
                                  <span className="flex items-center gap-1 text-xs font-medium text-amber-700">
                                    <Star className="size-3.5 fill-current" />
                                    {item.customer_rating} 星
                                  </span>
                                  {item.customer_comment && (
                                    <p className="mt-1 line-clamp-2 text-[10px] leading-4 text-muted-foreground">
                                      {item.customer_comment}
                                    </p>
                                  )}
                                </div>
                              ) : (
                                <span className="text-xs text-muted-foreground">待评价</span>
                              )}
                            </TableCell>
                            <TableCell>
                              {failedChecks.length ? (
                                <div className="flex max-w-md flex-wrap gap-1.5">
                                  {failedChecks.map((check) => (
                                    <Badge key={check.key} variant="outline" className="text-[10px]">
                                      {check.label}
                                    </Badge>
                                  ))}
                                </div>
                              ) : (
                                <span className="flex items-center gap-1.5 text-xs text-emerald-700">
                                  <CheckCircle2 className="size-3.5" /> 全部通过
                                </span>
                              )}
                            </TableCell>
                            <TableCell className="pr-4 text-xs text-muted-foreground">
                              {new Date(item.resolved_at).toLocaleString('zh-CN')}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                ) : (
                  <EmptyState icon={ClipboardCheck} text="暂无已解决的人工工单可供质检。" />
                )}
              </CardContent>
            </Card>

            <section className="grid gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(300px,0.6fr)]">
              <Card>
                <CardHeader>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <CardTitle>工单下钻</CardTitle>
                      <CardDescription className="mt-1">
                        按处理组与 SLA 状态筛选，并导出当前结果
                      </CardDescription>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!ticketReport?.items.length || reportLoading}
                      onClick={() => ticketReport && downloadTicketReport(ticketReport)}
                    >
                      <Download /> 导出 CSV
                    </Button>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Select
                      value={supportGroup}
                      onValueChange={(value) => value && setSupportGroup(value)}
                    >
                      <SelectTrigger className="w-[150px]" aria-label="处理组筛选">
                        <SelectValue placeholder="全部处理组" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="ALL">全部处理组</SelectItem>
                        {ticketReport?.available_support_groups.map((group) => (
                          <SelectItem key={group} value={group}>
                            {group}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Select
                      value={slaStatus}
                      onValueChange={(value) => value && setSlaStatus(value)}
                    >
                      <SelectTrigger className="w-[140px]" aria-label="SLA 状态筛选">
                        <SelectValue placeholder="全部 SLA" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="ALL">全部 SLA</SelectItem>
                        <SelectItem value="RISK">全部风险</SelectItem>
                        <SelectItem value="ON_TRACK">正常</SelectItem>
                        <SelectItem value="DUE_SOON">即将到期</SelectItem>
                        <SelectItem value="BREACHED">已超时</SelectItem>
                        <SelectItem value="COMPLETED">已完成</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  {ticketReport && !reportLoading && (
                    <p
                      className="mt-2 text-xs text-muted-foreground"
                      aria-label="筛选结果统计"
                    >
                      当前 {ticketReport.total} 张 · 风险 {ticketReport.risk} 张 ·
                      已超时 {ticketReport.breached} 张
                    </p>
                  )}
                </CardHeader>
                <CardContent className="px-0">
                  {reportLoading ? (
                    <div className="flex justify-center py-12 text-sm text-muted-foreground">
                      <Loader2 className="mr-2 size-4 animate-spin" /> 正在筛选工单…
                    </div>
                  ) : reportError ? (
                    <EmptyState icon={CircleAlert} text={reportError} />
                  ) : ticketReport?.items.length ? (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="pl-4">工单</TableHead>
                          <TableHead>客户</TableHead>
                          <TableHead>类型</TableHead>
                          <TableHead>优先级</TableHead>
                          <TableHead>处理队列</TableHead>
                          <TableHead className="pr-4">SLA</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {ticketReport.items.map((ticket) => (
                          <TableRow key={ticket.id}>
                            <TableCell className="pl-4">
                              <p className="font-medium">{ticket.ticket_number}</p>
                              <p className="mt-1 text-[11px] text-muted-foreground">{ticket.order_number}</p>
                            </TableCell>
                            <TableCell>{ticket.customer_name}</TableCell>
                            <TableCell>{ticketTypeLabel(ticket.ticket_type)}</TableCell>
                            <TableCell><Badge variant="outline">{ticket.priority}</Badge></TableCell>
                            <TableCell>{ticket.support_group}</TableCell>
                            <TableCell className="pr-4"><SlaBadge status={ticket.sla_status} /></TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  ) : (
                    <EmptyState icon={TicketCheck} text="当前筛选条件下没有工单。" />
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>工单类型分布</CardTitle>
                  <CardDescription>当前全部工单构成</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {dashboard.ticket_types.map((item) => {
                    const percent = dashboard.tickets.total
                      ? Math.round((item.count / dashboard.tickets.total) * 100)
                      : 0;
                    return (
                      <Progress key={item.type} value={percent}>
                        <ProgressLabel>{item.label}</ProgressLabel>
                        <span className="ml-auto text-sm tabular-nums text-muted-foreground">
                          {item.count}
                        </span>
                      </Progress>
                    );
                  })}
                </CardContent>
              </Card>
            </section>

            <Card>
              <CardHeader>
                <CardTitle>最近工具调用</CardTitle>
                <CardDescription>用于定位 Agent 执行失败与耗时异常</CardDescription>
              </CardHeader>
              <CardContent>
                {dashboard.recent_tools.length ? (
                  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                    {dashboard.recent_tools.map((tool) => (
                      <div className="rounded-xl border bg-[#fbfcfc] p-3" key={tool.id}>
                        <div className="flex items-center justify-between gap-2">
                          <span className="flex items-center gap-2 text-xs font-semibold">
                            <Bot className="size-4 text-primary" /> {tool.tool_name}
                          </span>
                          <span className={`size-2 rounded-full ${tool.status === 'SUCCEEDED' ? 'bg-emerald-500' : 'bg-red-500'}`} />
                        </div>
                        <div className="mt-3 flex justify-between text-[11px] text-muted-foreground">
                          <span>{tool.status === 'SUCCEEDED' ? '成功' : tool.error_type ?? '失败'}</span>
                          <span className="tabular-nums">{tool.duration_ms} ms</span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyState icon={Bot} text="暂无工具调用记录。" />
                )}
              </CardContent>
            </Card>
          </>
        ) : null}
      </div>
    </main>
  );
}

function downloadTicketReport(report: OperationsTicketReportData) {
  const rows = [
    ['工单编号', '订单编号', '客户', '类型', '优先级', '处理组', '当前负责人', 'SLA', '更新时间'],
    ...report.items.map((ticket) => [
      ticket.ticket_number,
      ticket.order_number,
      ticket.customer_name,
      ticketTypeLabel(ticket.ticket_type),
      ticket.priority,
      ticket.support_group,
      ticket.assignee_name ?? 'Agent 自动处理',
      slaText(ticket.sla_status),
      new Date(ticket.updated_at).toLocaleString('zh-CN'),
    ]),
  ];
  const csv = `\uFEFF${rows
    .map((row) => row.map(csvCell).join(','))
    .join('\r\n')}`;
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = `harbor-tickets-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function AlertConnectionBadge({
  status,
}: {
  status: 'CONNECTING' | 'LIVE' | 'RECONNECTING';
}) {
  const state = {
    CONNECTING: ['正在连接', 'bg-amber-50 text-amber-700', 'bg-amber-500'],
    LIVE: ['实时已连接', 'bg-emerald-50 text-emerald-700', 'bg-emerald-500'],
    RECONNECTING: ['正在重连', 'bg-red-50 text-red-700', 'bg-red-500'],
  }[status];
  return (
    <Badge
      aria-label="实时告警状态"
      className={`gap-2 ${state[1]}`}
      variant="secondary"
    >
      <span className={`size-2 rounded-full ${state[2]}`} /> {state[0]}
    </Badge>
  );
}

function AlertCard({
  alert,
  acknowledging,
  onAcknowledge,
}: {
  alert: OperationsAlertSnapshotData['items'][number];
  acknowledging: boolean;
  onAcknowledge: () => void;
}) {
  const tone = {
    CRITICAL: 'border-red-200 bg-red-50/70 text-red-800',
    HIGH: 'border-amber-200 bg-amber-50/70 text-amber-800',
    MEDIUM: 'border-sky-200 bg-sky-50/70 text-sky-800',
  }[alert.severity];
  const severityLabel = {
    CRITICAL: '紧急',
    HIGH: '高优先',
    MEDIUM: '待受理',
  }[alert.severity];
  return (
    <article className={`rounded-xl border p-4 ${tone}`} data-alert-ticket={alert.ticket_id}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" />
          <div className="min-w-0">
            <p className="text-sm font-semibold">{alert.title}</p>
            <p className="mt-1 text-xs leading-5 opacity-85">{alert.detail}</p>
          </div>
        </div>
        <Badge className="shrink-0 bg-white/75 text-current" variant="secondary">
          {severityLabel}
        </Badge>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-current/10 pt-3 text-[11px] opacity-80">
        <span>{alert.customer_name}</span>
        <span>{alert.order_number}</span>
        <span>{alert.support_group}</span>
        <span>{alert.priority}</span>
      </div>
      <div className="mt-3 flex min-h-7 items-center justify-end">
        {alert.acknowledged ? (
          <p
            aria-label={`告警确认状态 ${alert.ticket_number}`}
            className="flex items-center gap-1.5 text-[11px] font-medium"
          >
            <CheckCircle2 className="size-3.5" /> 已由 {alert.acknowledged_by} 确认 ·{' '}
            {alert.acknowledged_at
              ? new Date(alert.acknowledged_at).toLocaleString('zh-CN')
              : ''}
          </p>
        ) : (
          <Button
            aria-label={`确认知悉 ${alert.ticket_number}`}
            className="border-current/20 bg-white/80 text-current hover:bg-white"
            disabled={acknowledging}
            onClick={onAcknowledge}
            size="xs"
            variant="outline"
          >
            {acknowledging ? <Loader2 className="animate-spin" /> : <CheckCircle2 />}
            确认知悉
          </Button>
        )}
      </div>
    </article>
  );
}

function csvCell(value: string) {
  const safeValue = /^[=+@-]/.test(value.trimStart()) ? `'${value}` : value;
  return `"${safeValue.replaceAll('"', '""')}"`;
}

function MetricCard({
  label,
  value,
  note,
  icon: Icon,
  tone,
}: {
  label: string;
  value: number;
  note: string;
  icon: typeof Headphones;
  tone: string;
}) {
  return (
    <Card aria-label={label}>
      <CardContent className="flex items-start justify-between">
        <div>
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="mt-2 text-3xl font-semibold tabular-nums">{value}</p>
          <p className="mt-2 text-xs text-muted-foreground">{note}</p>
        </div>
        <span className={`grid size-10 place-items-center rounded-xl ${tone}`}>
          <Icon className="size-5" />
        </span>
      </CardContent>
    </Card>
  );
}

function MiniMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border bg-[#fbfcfc] px-2 py-3">
      <p className="text-lg font-semibold tabular-nums">{value}</p>
      <p className="mt-1 text-[10px] text-muted-foreground">{label}</p>
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return <span className="flex items-center gap-1.5"><span className={`size-2 rounded-sm ${color}`} />{label}</span>;
}

function EmptyState({ icon: Icon, text }: { icon: typeof Bot; text: string }) {
  return (
    <div className="flex flex-col items-center py-10 text-center text-sm text-muted-foreground">
      <Icon className="mb-3 size-6 opacity-50" />
      {text}
    </div>
  );
}

function ticketTypeLabel(type: string) {
  return { SHIPPING: '物流异常', ORDER: '订单问题', REFUND: '退款申请', OTHER: '其他售后' }[type] ?? type;
}

function SlaBadge({ status }: { status: string }) {
  const labels: Record<string, string> = {
    ON_TRACK: '正常',
    DUE_SOON: '即将到期',
    BREACHED: '已超时',
    COMPLETED: '已完成',
  };
  const tone = status === 'BREACHED'
    ? 'bg-red-50 text-red-700'
    : status === 'DUE_SOON'
      ? 'bg-amber-50 text-amber-700'
      : 'bg-emerald-50 text-emerald-700';
  return <Badge className={tone} variant="secondary">{labels[status] ?? status}</Badge>;
}

function QualityBadge({ grade }: { grade: 'EXCELLENT' | 'QUALIFIED' | 'ATTENTION' }) {
  const label = {
    EXCELLENT: '优秀',
    QUALIFIED: '合格',
    ATTENTION: '待改进',
  }[grade];
  const tone = grade === 'EXCELLENT'
    ? 'bg-emerald-50 text-emerald-700'
    : grade === 'QUALIFIED'
      ? 'bg-sky-50 text-sky-700'
      : 'bg-amber-50 text-amber-700';
  return <Badge className={tone} variant="secondary">{label}</Badge>;
}

function slaText(status: string) {
  return {
    ON_TRACK: '正常',
    DUE_SOON: '即将到期',
    BREACHED: '已超时',
    COMPLETED: '已完成',
  }[status] ?? status;
}
