import { bearerHeaders, type AuthSessionData } from './auth-session';

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export type DevelopmentAccountData = {
  login_name: string;
  display_name: string;
  principal_type: 'CUSTOMER' | 'OPERATOR';
  role: string;
};

export type AgentEvent = {
  type:
    | 'ack'
    | 'thinking'
    | 'message_delta'
    | 'tool_started'
    | 'tool_completed'
    | 'approval_required'
    | 'business_state_changed'
    | 'order_selection_required'
    | 'active_order_changed'
    | 'model_fallback'
    | 'error'
    | 'response_completed';
  conversation_id: string;
  message_id: string;
  tool_call_id?: string;
  trace_id: string;
  order_id?: string;
  ticket_id?: string;
  refund_request_id?: string;
  event_id?: string;
  sequence?: number;
  phase?: 'ACK' | 'THINKING' | 'TOOL_CALL' | 'TOOL_RESULT' | 'FINAL_RESPONSE';
  payload: Record<string, unknown>;
};

export type TicketMessageData = {
  id: string;
  sender_role: 'CUSTOMER' | 'SUPPORT_AGENT';
  sender_name: string;
  content: string;
  created_at: string;
};

export type TicketData = {
  id: string;
  ticket_number: string;
  order_id: string;
  conversation_id: string;
  ticket_type: string;
  status: string;
  priority: string;
  handoff_status: string;
  assignee_name?: string;
  handoff_requested_at?: string;
  assigned_at?: string;
  sla_due_at: string;
  sla_status: string;
  sla_remaining_minutes: number;
  reason: string;
  resolution: {
    summary: string;
    handled_by: string;
    resolved_at: string;
  } | null;
  feedback: CustomerFeedbackData | null;
  messages: TicketMessageData[];
  created_at: string;
};

export type CustomerFeedbackData = {
  id: string;
  ticket_id: string;
  rating: number;
  comment: string | null;
  submitted_at: string;
};

export type RefundData = {
  id: string;
  refund_number: string;
  ticket_id: string;
  order_id: string;
  status: string;
  amount: string;
  method: string;
  reason: string;
  approved_by_operator_id?: string | null;
  approved_at?: string | null;
  confirmed_at?: string | null;
  created_at: string;
};

export type ConversationState = {
  conversation: {
    id: string;
    updated_at: string;
    order_selection_pending: boolean;
    pending_action: string | null;
    current_intent: string | null;
  };
  current_intent: string | null;
  intent_history: IntentHistoryData[];
  active_order: OrderData | null;
  order_selection: {
    required: boolean;
    orders: OrderData[];
  };
  messages: Array<{
    id: string;
    role: 'user' | 'agent';
    content: string;
    created_at: string;
  }>;
  tickets: TicketData[];
  refunds: RefundData[];
  tool_invocations: Array<{
    id: string;
    tool_call_id: string;
    tool_name: string;
    status: string;
    duration_ms: number;
    error_type?: string;
    created_at: string;
  }>;
};

export type OrderData = {
  id: string;
  order_number: string;
  product_name: string;
  paid_amount: string;
  refundable_amount: string;
  status: string;
  ordered_at: string;
};
export type ShippingData = {
  order_id: string;
  order_number: string;
  abnormal: boolean;
  abnormal_reason?: string;
  stale_hours: number;
  nodes: Array<{ location: string; description: string; occurred_at: string }>;
};

export type KnowledgeArticleData = {
  id: string;
  title: string;
  version: string;
  section: string;
  content: string;
  keywords: string[];
  source_uri: string;
  content_hash: string;
  active: boolean;
  valid_from: string;
  valid_until?: string;
  created_at: string;
};

export type KnowledgePublishData = {
  title: string;
  version: string;
  section: string;
  content: string;
  keywords: string[];
  source_uri: string;
};

export type OperationsDashboardData = {
  generated_at: string;
  tickets: {
    total: number;
    active: number;
    resolved: number;
    assigned: number;
    due_soon: number;
    breached: number;
  };
  refunds: {
    total: number;
    pending: number;
    succeeded: number;
    cancelled: number;
    total_refunded_amount: string;
  };
  tools: {
    total: number;
    succeeded: number;
    failed: number;
    success_rate: number;
    average_duration_ms: number;
  };
  models: {
    window_hours: number;
    total: number;
    succeeded: number;
    failed: number;
    fallback: number;
    success_rate: number;
    average_duration_ms: number;
    p95_duration_ms: number;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  };
  knowledge: { active: number; historical: number; versions: number };
  ticket_types: Array<{ type: string; label: string; count: number }>;
  activity: Array<{
    date: string;
    label: string;
    tickets: number;
    refunds: number;
    tools: number;
  }>;
  recent_tickets: Array<{
    id: string;
    ticket_number: string;
    order_number: string;
    ticket_type: string;
    status: string;
    priority: string;
    handoff_status: string;
    assignee_name?: string;
    sla_status: string;
    sla_remaining_minutes: number;
    created_at: string;
  }>;
  recent_tools: Array<{
    id: string;
    tool_name: string;
    status: string;
    duration_ms: number;
    error_type?: string;
    created_at: string;
  }>;
  recent_model_invocations: Array<{
    id: string;
    provider: string;
    model_name: string;
    status: string;
    duration_ms: number;
    total_tokens: number;
    error_type?: string;
    fallback_used: boolean;
    created_at: string;
  }>;
};

export type CommerceIntegrationStatusData = {
  provider: 'TAOBAO' | 'XIAOHONGSHU' | 'XIANYU';
  state: 'NOT_CONFIGURED' | 'READY' | 'DEGRADED';
  capabilities: Array<'IDENTITY' | 'ORDERS_READ' | 'SHIPPING_READ'>;
  external_requests_enabled: boolean;
  message: string;
};

export type OperationsTicketReportData = {
  generated_at: string;
  selected_support_group: string | null;
  selected_sla_status: string | null;
  available_support_groups: string[];
  total: number;
  risk: number;
  breached: number;
  items: Array<{
    id: string;
    ticket_number: string;
    order_number: string;
    customer_name: string;
    ticket_type: string;
    priority: string;
    status: string;
    handoff_status: string;
    support_group: string;
    assignee_name?: string;
    sla_status: string;
    sla_remaining_minutes: number;
    updated_at: string;
  }>;
};

export type OperationsAlertSnapshotData = {
  generated_at: string;
  total: number;
  unacknowledged: number;
  critical: number;
  high: number;
  medium: number;
  items: Array<{
    id: string;
    type: 'SLA_BREACHED' | 'SLA_DUE_SOON' | 'HANDOFF_QUEUED';
    severity: 'CRITICAL' | 'HIGH' | 'MEDIUM';
    title: string;
    detail: string;
    ticket_id: string;
    ticket_number: string;
    order_number: string;
    customer_name: string;
    support_group: string;
    priority: string;
    sla_status: string;
    sla_remaining_minutes: number;
    triggered_at: string;
    acknowledged: boolean;
    acknowledged_by: string | null;
    acknowledged_at: string | null;
  }>;
};

export type OperationsAlertAcknowledgementData = {
  id: string;
  ticket_id: string;
  alert_type: string;
  acknowledged_by: string;
  acknowledged_at: string;
};

export type OperationsQualityReportData = {
  generated_at: string;
  total: number;
  excellent: number;
  qualified: number;
  attention: number;
  average_score: number;
  feedback_received: number;
  low_ratings: number;
  average_customer_rating: number;
  items: Array<{
    ticket_id: string;
    ticket_number: string;
    order_number: string;
    customer_name: string;
    support_group: string;
    assignee_name: string;
    resolved_at: string;
    score: number;
    grade: 'EXCELLENT' | 'QUALIFIED' | 'ATTENTION';
    checks: Array<{
      key: string;
      label: string;
      passed: boolean;
      score: number;
      max_score: number;
    }>;
    customer_rating: number | null;
    customer_comment: string | null;
    feedback_submitted_at: string | null;
  }>;
};

export type OperationsAlertEvent =
  | { type: 'operations_alert_snapshot'; snapshot: OperationsAlertSnapshotData }
  | { type: 'heartbeat' };

export type AgentProfileData = {
  id: string;
  name: string;
  role: string;
};

export type AgentTicketData = {
  id: string;
  ticket_number: string;
  conversation_id: string;
  order_number: string;
  customer_name: string;
  product_name: string;
  ticket_type: string;
  status: string;
  priority: string;
  handoff_status: string;
  work_state: 'QUEUED' | 'IN_PROGRESS' | 'RESOLVED';
  support_group: string;
  assignee_name?: string;
  is_mine: boolean;
  sla_due_at: string;
  sla_status: string;
  sla_remaining_minutes: number;
  reason: string;
  evidence: Record<string, unknown>;
  version: number;
  created_at: string;
  updated_at: string;
  messages: TicketMessageData[];
  events: Array<{
    action: string;
    detail: string;
    actor: string;
    created_at: string;
  }>;
  refund: RefundData | null;
  current_intent: string | null;
  intent_history: IntentHistoryData[];
};

export type IntentHistoryData = {
  id: string;
  intent: string;
  previous_intent: string | null;
  actor: string;
  source: string;
  source_ticket_id: string | null;
  related_ticket_id: string | null;
  related_refund_id: string | null;
  detail: string;
  created_at: string;
};

export type AgentQueueEvent =
  | { type: 'ticket_queue_snapshot'; tickets: AgentTicketData[] }
  | { type: 'heartbeat' };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set('Content-Type', 'application/json');
  for (const [name, value] of Object.entries(bearerHeaders('customer'))) {
    headers.set(name, value);
  }
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    throw new Error(body?.error?.message ?? `请求失败（${response.status}）`);
  }
  return response.json() as Promise<T>;
}

async function opsRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set('Content-Type', 'application/json');
  for (const [name, value] of Object.entries(bearerHeaders('staff'))) {
    headers.set(name, value);
  }
  const response = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    throw new Error(body?.error?.message ?? `请求失败（${response.status}）`);
  }
  return response.json() as Promise<T>;
}

async function agentRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set('Content-Type', 'application/json');
  for (const [name, value] of Object.entries(bearerHeaders('staff'))) {
    headers.set(name, value);
  }
  const response = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    throw new Error(body?.error?.message ?? `请求失败（${response.status}）`);
  }
  return response.json() as Promise<T>;
}

export async function listDevelopmentAccounts() {
  const response = await fetch(`${API_URL}/api/auth/development-accounts`);
  if (!response.ok) throw new Error('开发账号服务不可用');
  return response.json() as Promise<DevelopmentAccountData[]>;
}

export async function loginDevelopmentAccount(
  loginName: string,
  password: string,
) {
  const response = await fetch(`${API_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ login_name: loginName, password }),
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    throw new Error(body?.error?.message ?? '登录失败');
  }
  return response.json() as Promise<AuthSessionData>;
}

export async function logoutAuthSession(accessToken: string) {
  const response = await fetch(`${API_URL}/api/auth/logout`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!response.ok && response.status !== 401) {
    throw new Error('退出登录失败');
  }
}

export const createConversation = () =>
  request<{ id: string; customer_name: string }>('/api/conversations', {
    method: 'POST',
  });
export const loadConversation = (id: string) =>
  request<ConversationState>(`/api/conversations/${id}`);
export const listRecentOrders = () =>
  request<OrderData[]>('/api/orders/recent');
export const requestOrderSelection = (conversationId: string) =>
  request<OrderData[]>(`/api/conversations/${conversationId}/order-selection`, {
    method: 'POST',
  });
export const selectActiveOrder = (
  conversationId: string,
  orderNumber: string,
) =>
  request<OrderData>(`/api/conversations/${conversationId}/active-order`, {
    method: 'POST',
    body: JSON.stringify({ order_number: orderNumber }),
  });
export const getOrder = (number = 'ORD-20260828-1042') =>
  request<OrderData>(`/api/orders/${number}`);
export const getShipping = (number = 'ORD-20260828-1042') =>
  request<ShippingData>(`/api/orders/${number}/shipping`);

export async function sendMessage(
  conversationId: string,
  content: string,
  onEvent: (event: AgentEvent) => void,
) {
  const response = await fetch(
    `${API_URL}/api/conversations/${conversationId}/messages`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...bearerHeaders('customer'),
      },
      body: JSON.stringify({ content }),
    },
  );
  if (!response.ok || !response.body) {
    const body = (await response.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    throw new Error(body?.error?.message ?? 'Agent 服务暂时不可用');
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines)
      if (line.trim()) onEvent(JSON.parse(line) as AgentEvent);
    if (done) break;
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer) as AgentEvent);
}

export const createShippingTicket = (
  conversationId: string,
  orderNumber: string,
) =>
  request<ConversationState['tickets'][number] & { events: unknown[] }>(
    '/api/tickets',
    {
      method: 'POST',
      body: JSON.stringify({
        conversation_id: conversationId,
        order_number: orderNumber,
        ticket_type: 'SHIPPING',
        reason: '物流长时间未更新',
      }),
    },
  );

export const handoffTicket = (ticketId: string) =>
  request<TicketData & { events: unknown[] }>(
    `/api/tickets/${ticketId}/handoff`,
    { method: 'POST' },
  );

export const cancelTicketHandoff = (ticketId: string) =>
  request<TicketData & { events: unknown[] }>(
    `/api/tickets/${ticketId}/handoff/cancel`,
    { method: 'POST' },
  );

export const sendCustomerTicketMessage = (ticketId: string, content: string) =>
  request<TicketData & { events: unknown[] }>(
    `/api/tickets/${ticketId}/messages`,
    {
      method: 'POST',
      body: JSON.stringify({ content }),
    },
  );

export const submitCustomerFeedback = (
  ticketId: string,
  rating: number,
  comment: string,
) =>
  request<CustomerFeedbackData>(`/api/tickets/${ticketId}/feedback`, {
    method: 'POST',
    body: JSON.stringify({ rating, comment: comment.trim() || null }),
  });

export const confirmRefund = (refundId: string, key: string) =>
  request<ConversationState['refunds'][number]>(
    `/api/refund-requests/${refundId}/confirm`,
    { method: 'POST', headers: { 'Idempotency-Key': key } },
  );

export const cancelRefund = (refundId: string) =>
  request<ConversationState['refunds'][number]>(
    `/api/refund-requests/${refundId}/cancel`,
    { method: 'POST' },
  );

export const listKnowledgeArticles = () =>
  opsRequest<KnowledgeArticleData[]>('/api/ops/knowledge');

export const publishKnowledgeArticle = (body: KnowledgePublishData) =>
  opsRequest<KnowledgeArticleData>('/api/ops/knowledge', {
    method: 'POST',
    body: JSON.stringify(body),
  });

export const deactivateKnowledgeArticle = (articleId: string) =>
  opsRequest<KnowledgeArticleData>(
    `/api/ops/knowledge/${articleId}/deactivate`,
    { method: 'POST' },
  );

export const getOperationsDashboard = () =>
  opsRequest<OperationsDashboardData>('/api/ops/dashboard');

export const getCommerceIntegrationStatuses = () =>
  opsRequest<CommerceIntegrationStatusData[]>('/api/ops/integrations/commerce');

export const getOperationsQualityReport = () =>
  opsRequest<OperationsQualityReportData>('/api/ops/quality-reviews');

export const getOperationsTicketReport = (filters?: {
  supportGroup?: string;
  slaStatus?: string;
}) => {
  const params = new URLSearchParams();
  if (filters?.supportGroup) params.set('support_group', filters.supportGroup);
  if (filters?.slaStatus) params.set('sla_status', filters.slaStatus);
  const query = params.size ? `?${params.toString()}` : '';
  return opsRequest<OperationsTicketReportData>(`/api/ops/tickets${query}`);
};

export async function streamOperationsAlerts(
  onEvent: (event: OperationsAlertEvent) => void,
  signal: AbortSignal,
) {
  const response = await fetch(`${API_URL}/api/ops/alerts/stream`, {
    headers: bearerHeaders('staff'),
    signal,
  });
  if (!response.ok || !response.body) {
    const body = (await response.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    throw new Error(body?.error?.message ?? '实时运营告警连接失败');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      if (line.trim()) onEvent(JSON.parse(line) as OperationsAlertEvent);
    }
    if (done) break;
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer) as OperationsAlertEvent);
}

export const acknowledgeOperationsAlert = (ticketId: string, alertType: string) =>
  opsRequest<OperationsAlertAcknowledgementData>(
    `/api/ops/alerts/${ticketId}/${alertType}/acknowledge`,
    { method: 'POST' },
  );

export const getAgentProfile = () =>
  agentRequest<AgentProfileData>('/api/agent/me');

export const listAgentTickets = () =>
  agentRequest<AgentTicketData[]>('/api/agent/tickets');

export async function streamAgentTickets(
  onEvent: (event: AgentQueueEvent) => void,
  signal: AbortSignal,
) {
  const response = await fetch(`${API_URL}/api/agent/tickets/stream`, {
    headers: bearerHeaders('staff'),
    signal,
  });
  if (!response.ok || !response.body) {
    const body = (await response.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    throw new Error(body?.error?.message ?? '实时工单连接失败');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      if (line.trim()) onEvent(JSON.parse(line) as AgentQueueEvent);
    }
    if (done) break;
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer) as AgentQueueEvent);
}

export const acceptAgentTicket = (ticketId: string) =>
  agentRequest<AgentTicketData>(
    `/api/agent/tickets/${ticketId}/accept`,
    { method: 'POST' },
  );

export const changeAgentTicketIntent = (
  ticketId: string,
  body: { intent: 'REFUND'; reason: string; order_number?: string },
) =>
  agentRequest<AgentTicketData>(`/api/agent/tickets/${ticketId}/intent`, {
    method: 'POST',
    body: JSON.stringify(body),
  });

export const addAgentTicketNote = (
  ticketId: string,
  content: string,
) =>
  agentRequest<AgentTicketData>(
    `/api/agent/tickets/${ticketId}/notes`,
    {
      method: 'POST',
      body: JSON.stringify({ content }),
    },
  );

export const sendAgentTicketMessage = (
  ticketId: string,
  content: string,
) =>
  agentRequest<AgentTicketData>(
    `/api/agent/tickets/${ticketId}/messages`,
    {
      method: 'POST',
      body: JSON.stringify({ content }),
    },
  );

export const resolveAgentTicket = (
  ticketId: string,
  resolution: string,
) =>
  agentRequest<AgentTicketData>(
    `/api/agent/tickets/${ticketId}/resolve`,
    {
      method: 'POST',
      body: JSON.stringify({ resolution }),
    },
  );

export const approveAgentRefund = (refundId: string, key: string) =>
  agentRequest<RefundData>(
    `/api/agent/refund-requests/${refundId}/approve`,
    { method: 'POST', headers: { 'Idempotency-Key': key } },
  );

export const rejectAgentRefund = (
  refundId: string,
  key: string,
  reason: string,
) =>
  agentRequest<RefundData>(
    `/api/agent/refund-requests/${refundId}/reject`,
    {
      method: 'POST',
      headers: { 'Idempotency-Key': key },
      body: JSON.stringify({ reason }),
    },
  );

export const withdrawAgentRefund = (
  refundId: string,
  key: string,
  reason: string,
) =>
  agentRequest<RefundData>(
    `/api/agent/refund-requests/${refundId}/withdraw`,
    {
      method: 'POST',
      headers: { 'Idempotency-Key': key },
      body: JSON.stringify({ reason }),
    },
  );
