export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
export const DEMO_SESSION = 'demo-linmu-session';

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
