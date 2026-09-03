export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
export const DEMO_SESSION = 'demo-linmu-session';
export const OPS_SESSION = 'demo-knowledge-ops-session';
export const AGENT_SESSIONS = [
  { token: 'demo-support-agent-session', name: '沈清禾' },
  { token: 'demo-support-agent-luchuan-session', name: '陆川' },
] as const;

export type AgentEvent = {
  type:
    | 'message_delta'
    | 'tool_started'
    | 'tool_completed'
    | 'approval_required'
    | 'business_state_changed'
    | 'error'
    | 'response_completed';
  conversation_id: string;
  message_id: string;
  tool_call_id?: string;
  trace_id: string;
  order_id?: string;
  ticket_id?: string;
  refund_request_id?: string;
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
  messages: TicketMessageData[];
  created_at: string;
};

export type ConversationState = {
  conversation: { id: string; updated_at: string };
  messages: Array<{
    id: string;
    role: 'user' | 'agent';
    content: string;
    created_at: string;
  }>;
  tickets: TicketData[];
  refunds: Array<{
    id: string;
    refund_number: string;
    ticket_id: string;
    status: string;
    amount: string;
    method: string;
    reason: string;
    created_at: string;
  }>;
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
};

export type AgentQueueEvent =
  | { type: 'ticket_queue_snapshot'; tickets: AgentTicketData[] }
  | { type: 'heartbeat' };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set('Content-Type', 'application/json');
  headers.set('X-Demo-Session', DEMO_SESSION);
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
  headers.set('X-Ops-Session', OPS_SESSION);
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
  sessionToken: string,
  init?: RequestInit,
): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set('Content-Type', 'application/json');
  headers.set('X-Agent-Session', sessionToken);
  const response = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    throw new Error(body?.error?.message ?? `请求失败（${response.status}）`);
  }
  return response.json() as Promise<T>;
}

export const createConversation = () =>
  request<{ id: string; customer_name: string }>('/api/conversations', {
    method: 'POST',
  });
export const loadConversation = (id: string) =>
  request<ConversationState>(`/api/conversations/${id}`);
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
        'X-Demo-Session': DEMO_SESSION,
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

export const getAgentProfile = (sessionToken: string) =>
  agentRequest<AgentProfileData>('/api/agent/me', sessionToken);

export const listAgentTickets = (sessionToken: string) =>
  agentRequest<AgentTicketData[]>('/api/agent/tickets', sessionToken);

export async function streamAgentTickets(
  sessionToken: string,
  onEvent: (event: AgentQueueEvent) => void,
  signal: AbortSignal,
) {
  const response = await fetch(`${API_URL}/api/agent/tickets/stream`, {
    headers: { 'X-Agent-Session': sessionToken },
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

export const acceptAgentTicket = (sessionToken: string, ticketId: string) =>
  agentRequest<AgentTicketData>(
    `/api/agent/tickets/${ticketId}/accept`,
    sessionToken,
    { method: 'POST' },
  );

export const addAgentTicketNote = (
  sessionToken: string,
  ticketId: string,
  content: string,
) =>
  agentRequest<AgentTicketData>(
    `/api/agent/tickets/${ticketId}/notes`,
    sessionToken,
    {
      method: 'POST',
      body: JSON.stringify({ content }),
    },
  );

export const sendAgentTicketMessage = (
  sessionToken: string,
  ticketId: string,
  content: string,
) =>
  agentRequest<AgentTicketData>(
    `/api/agent/tickets/${ticketId}/messages`,
    sessionToken,
    {
      method: 'POST',
      body: JSON.stringify({ content }),
    },
  );

export const resolveAgentTicket = (
  sessionToken: string,
  ticketId: string,
  resolution: string,
) =>
  agentRequest<AgentTicketData>(
    `/api/agent/tickets/${ticketId}/resolve`,
    sessionToken,
    {
      method: 'POST',
      body: JSON.stringify({ resolution }),
    },
  );
