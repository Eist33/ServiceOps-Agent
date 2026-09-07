import {
  XIANYU_LOCAL_PAGE_VERSION,
  type XianyuLocalConnection,
} from './xianyu-local-session.ts';
import { clientId } from './client-id.ts';

/**
 * 9B-5 is deliberately a local, platform-neutral approval contract.  It
 * records an operator decision but has no transport and therefore cannot send
 * anything to Xianyu or another external platform.
 */
export const XIANYU_REPLY_WORKFLOW_SCHEMA_VERSION = 1;
export const XIANYU_REPLY_WORKFLOW_STORAGE_KEY =
  'harbor-support-xianyu-local-reply-workflow';
export const XIANYU_REPLY_TAB_REF_STORAGE_KEY =
  'harbor-support-xianyu-local-reply-tab-ref';
export const XIANYU_REPLY_DRAFT_MAX_LENGTH = 2_000;
export const XIANYU_REPLY_DRAFT_DEFAULT_TTL_MS = 10 * 60 * 1_000;
export const XIANYU_REPLY_DRAFT_MAX_TTL_MS = 15 * 60 * 1_000;
export const XIANYU_REPLY_AUDIT_MAX_EVENTS = 50;

export type ReplyActorRole =
  | 'SUPPORT_AGENT'
  | 'CUSTOMER'
  | 'OPERATIONS_MANAGER'
  | 'UNKNOWN';

export type ReplyDraftStatus =
  | 'DRAFTED'
  | 'APPROVED'
  | 'SEND_BLOCKED_NOT_CONFIGURED'
  | 'EXPIRED'
  | 'REJECTED'
  | 'FAILED_CLOSED';

export type ReplyContext = {
  tab_ref: string;
  connection_ref: string;
  account_ref: string;
  conversation_ref: string;
  source_page_version: string;
  detail_read_at: string;
};

export type ReplyDraft = {
  schema_version: typeof XIANYU_REPLY_WORKFLOW_SCHEMA_VERSION;
  draft_id: string;
  context: ReplyContext;
  body: string;
  created_at: string;
  expires_at: string;
  status: ReplyDraftStatus;
  approved_by_role: ReplyActorRole | null;
  approved_at: string | null;
  approval_action_id: string | null;
  send_action_id: string | null;
  send_requested_at: string | null;
  failure_code: ReplyFailureCode | null;
};

export type ReplyFailureCode =
  | 'INVALID_INPUT'
  | 'ROLE_NOT_ALLOWED'
  | 'CONTEXT_MISMATCH'
  | 'PAGE_CHANGED'
  | 'DRAFT_EXPIRED'
  | 'REVIEW_REQUIRED'
  | 'ALREADY_APPROVED'
  | 'CONFIRMATION_REQUIRED'
  | 'SEND_ALREADY_REQUESTED'
  | 'NOT_CONFIGURED'
  | 'DRAFT_REJECTED'
  | 'INVALID_STATE';

export type ReplyAuditEventType =
  | 'DRAFT_CREATED'
  | 'DRAFT_APPROVED'
  | 'APPROVAL_REPLAYED'
  | 'DRAFT_REJECTED'
  | 'SEND_BLOCKED_NOT_CONFIGURED'
  | 'SEND_REPLAYED'
  | 'DRAFT_EXPIRED'
  | 'CONTEXT_FAILED_CLOSED'
  | 'ROLE_DENIED'
  | 'CONFIRMATION_REQUIRED'
  | 'INPUT_REJECTED';

export type ReplyAuditEvent = {
  schema_version: typeof XIANYU_REPLY_WORKFLOW_SCHEMA_VERSION;
  event_id: string;
  event_type: ReplyAuditEventType;
  draft_id: string;
  connection_ref: string;
  account_ref: string;
  conversation_ref: string;
  actor_role: ReplyActorRole;
  occurred_at: string;
  reason: ReplyFailureCode | null;
  body_length: number;
};

export type ReplyWorkflowSnapshot = {
  schema_version: typeof XIANYU_REPLY_WORKFLOW_SCHEMA_VERSION;
  draft: ReplyDraft;
  audit_events: readonly ReplyAuditEvent[];
};

export type CreateReplyDraftInput = {
  context: ReplyContext;
  body: string;
  now: string;
  draft_id?: string;
  ttl_ms?: number;
};

export type ApproveReplyDraftInput = {
  draft: ReplyDraft;
  actor_role: ReplyActorRole;
  current_context: ReplyContext;
  now: string;
  approval_action_id: string;
};

export type RejectReplyDraftInput = {
  draft: ReplyDraft;
  actor_role: ReplyActorRole;
  current_context: ReplyContext;
  now: string;
  rejection_action_id: string;
};

export type ExplicitSendInput = {
  draft: ReplyDraft;
  actor_role: ReplyActorRole;
  current_context: ReplyContext;
  now: string;
  send_action_id: string;
  confirmation: 'CONFIRM_SEND' | null;
};

export type ReplyWorkflowResult = {
  ok: boolean;
  status: ReplyDraftStatus | 'NO_DRAFT';
  draft: ReplyDraft | null;
  audit_event: ReplyAuditEvent;
  error_code: ReplyFailureCode | null;
  error_message: string | null;
  external_request_started: false;
  sent: false;
  user_action_required: 'REVIEW' | 'MANUAL_SEND_ON_OFFICIAL_PAGE' | 'NONE';
};

export interface HumanApprovedReplyWorkflow {
  createDraft(input: CreateReplyDraftInput): ReplyWorkflowResult;
  approveDraft(input: ApproveReplyDraftInput): ReplyWorkflowResult;
  rejectDraft(input: RejectReplyDraftInput): ReplyWorkflowResult;
  requestExplicitSend(input: ExplicitSendInput): ReplyWorkflowResult;
}

const DRAFT_FIELDS = [
  'schema_version',
  'draft_id',
  'context',
  'body',
  'created_at',
  'expires_at',
  'status',
  'approved_by_role',
  'approved_at',
  'approval_action_id',
  'send_action_id',
  'send_requested_at',
  'failure_code',
] as const;
const CONTEXT_FIELDS = [
  'tab_ref',
  'connection_ref',
  'account_ref',
  'conversation_ref',
  'source_page_version',
  'detail_read_at',
] as const;
const AUDIT_FIELDS = [
  'schema_version',
  'event_id',
  'event_type',
  'draft_id',
  'connection_ref',
  'account_ref',
  'conversation_ref',
  'actor_role',
  'occurred_at',
  'reason',
  'body_length',
] as const;
const SNAPSHOT_FIELDS = ['schema_version', 'draft', 'audit_events'] as const;

const REPLY_ACTOR_ROLES: readonly ReplyActorRole[] = [
  'SUPPORT_AGENT',
  'CUSTOMER',
  'OPERATIONS_MANAGER',
  'UNKNOWN',
];
const REPLY_STATUSES: readonly ReplyDraftStatus[] = [
  'DRAFTED',
  'APPROVED',
  'SEND_BLOCKED_NOT_CONFIGURED',
  'EXPIRED',
  'REJECTED',
  'FAILED_CLOSED',
];
const REPLY_FAILURE_CODES: readonly ReplyFailureCode[] = [
  'INVALID_INPUT',
  'ROLE_NOT_ALLOWED',
  'CONTEXT_MISMATCH',
  'PAGE_CHANGED',
  'DRAFT_EXPIRED',
  'REVIEW_REQUIRED',
  'ALREADY_APPROVED',
  'CONFIRMATION_REQUIRED',
  'SEND_ALREADY_REQUESTED',
  'NOT_CONFIGURED',
  'DRAFT_REJECTED',
  'INVALID_STATE',
];
const REPLY_EVENT_TYPES: readonly ReplyAuditEventType[] = [
  'DRAFT_CREATED',
  'DRAFT_APPROVED',
  'APPROVAL_REPLAYED',
  'DRAFT_REJECTED',
  'SEND_BLOCKED_NOT_CONFIGURED',
  'SEND_REPLAYED',
  'DRAFT_EXPIRED',
  'CONTEXT_FAILED_CLOSED',
  'ROLE_DENIED',
  'CONFIRMATION_REQUIRED',
  'INPUT_REJECTED',
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function hasExactFields(
  value: Record<string, unknown>,
  fields: readonly string[],
): boolean {
  const keys = Object.keys(value);
  return (
    keys.length === fields.length &&
    fields.every((field) => Object.hasOwn(value, field))
  );
}

function isIsoDate(value: unknown): value is string {
  return typeof value === 'string' && Number.isFinite(Date.parse(value));
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function isReplyActorRole(value: unknown): value is ReplyActorRole {
  return REPLY_ACTOR_ROLES.includes(value as ReplyActorRole);
}

function isReplyStatus(value: unknown): value is ReplyDraftStatus {
  return REPLY_STATUSES.includes(value as ReplyDraftStatus);
}

function isReplyFailureCode(value: unknown): value is ReplyFailureCode {
  return REPLY_FAILURE_CODES.includes(value as ReplyFailureCode);
}

function isReplyEventType(value: unknown): value is ReplyAuditEventType {
  return REPLY_EVENT_TYPES.includes(value as ReplyAuditEventType);
}

function createOpaqueId(prefix: string): string {
  return clientId(prefix);
}

function validTimestampOrder(start: string, end: string): boolean {
  return (
    isIsoDate(start) && isIsoDate(end) && Date.parse(start) <= Date.parse(end)
  );
}

function isValidContext(value: unknown): value is ReplyContext {
  if (!isRecord(value) || !hasExactFields(value, CONTEXT_FIELDS)) return false;
  return (
    isNonEmptyString(value.tab_ref) &&
    isNonEmptyString(value.connection_ref) &&
    isNonEmptyString(value.account_ref) &&
    isNonEmptyString(value.conversation_ref) &&
    isNonEmptyString(value.source_page_version) &&
    isIsoDate(value.detail_read_at)
  );
}

function sameContext(left: ReplyContext, right: ReplyContext): boolean {
  return (
    left.tab_ref === right.tab_ref &&
    left.connection_ref === right.connection_ref &&
    left.account_ref === right.account_ref &&
    left.conversation_ref === right.conversation_ref &&
    left.source_page_version === right.source_page_version &&
    left.detail_read_at === right.detail_read_at
  );
}

function hasCurrentContext(current: ReplyContext, draft: ReplyDraft): boolean {
  return isValidContext(current) && sameContext(current, draft.context);
}

function emptyDraftFields(): Pick<
  ReplyDraft,
  | 'approved_by_role'
  | 'approved_at'
  | 'approval_action_id'
  | 'send_action_id'
  | 'send_requested_at'
  | 'failure_code'
> {
  return {
    approved_by_role: null,
    approved_at: null,
    approval_action_id: null,
    send_action_id: null,
    send_requested_at: null,
    failure_code: null,
  };
}

function auditEvent(
  eventType: ReplyAuditEventType,
  draft: ReplyDraft | null,
  occurredAt: string,
  actorRole: ReplyActorRole,
  reason: ReplyFailureCode | null,
): ReplyAuditEvent {
  const context = draft && isValidContext(draft.context) ? draft.context : null;
  return {
    schema_version: XIANYU_REPLY_WORKFLOW_SCHEMA_VERSION,
    event_id: createOpaqueId('reply-audit'),
    event_type: eventType,
    draft_id:
      draft && isNonEmptyString(draft.draft_id) ? draft.draft_id : 'UNKNOWN',
    connection_ref: context?.connection_ref ?? 'UNKNOWN',
    account_ref: context?.account_ref ?? 'UNKNOWN',
    conversation_ref: context?.conversation_ref ?? 'UNKNOWN',
    actor_role: actorRole,
    occurred_at: occurredAt,
    reason,
    body_length:
      draft && typeof draft.body === 'string' ? draft.body.length : 0,
  };
}

function result(
  draft: ReplyDraft | null,
  event: ReplyAuditEvent,
  options: {
    ok: boolean;
    errorCode?: ReplyFailureCode | null;
    errorMessage?: string | null;
    userActionRequired?: ReplyWorkflowResult['user_action_required'];
  },
): ReplyWorkflowResult {
  return {
    ok: options.ok,
    status: draft?.status ?? 'NO_DRAFT',
    draft,
    audit_event: event,
    error_code: options.errorCode ?? null,
    error_message: options.errorMessage ?? null,
    external_request_started: false,
    sent: false,
    user_action_required: options.userActionRequired ?? 'NONE',
  };
}

function invalidInput(
  now: string,
  message: string,
  draft: ReplyDraft | null = null,
): ReplyWorkflowResult {
  return result(
    draft,
    auditEvent(
      'INPUT_REJECTED',
      draft,
      isIsoDate(now) ? now : new Date().toISOString(),
      'UNKNOWN',
      'INVALID_INPUT',
    ),
    {
      ok: false,
      errorCode: 'INVALID_INPUT',
      errorMessage: message,
    },
  );
}

function expiredDraft(
  draft: ReplyDraft,
  now: string,
  actorRole: ReplyActorRole,
): ReplyWorkflowResult {
  const next: ReplyDraft = {
    ...draft,
    status: 'EXPIRED',
    approved_by_role: null,
    approved_at: null,
    approval_action_id: null,
    send_action_id: null,
    send_requested_at: null,
    failure_code: 'DRAFT_EXPIRED',
  };
  return result(
    next,
    auditEvent('DRAFT_EXPIRED', next, now, actorRole, 'DRAFT_EXPIRED'),
    {
      ok: false,
      errorCode: 'DRAFT_EXPIRED',
      errorMessage: '回复草稿已过期，已失败关闭；请重新创建草稿。',
    },
  );
}

function failClosedContext(
  draft: ReplyDraft,
  now: string,
  actorRole: ReplyActorRole,
  reason: 'CONTEXT_MISMATCH' | 'PAGE_CHANGED',
): ReplyWorkflowResult {
  const next: ReplyDraft = {
    ...draft,
    status: 'FAILED_CLOSED',
    approved_by_role: null,
    approved_at: null,
    approval_action_id: null,
    send_action_id: null,
    send_requested_at: null,
    failure_code: reason,
  };
  return result(
    next,
    auditEvent('CONTEXT_FAILED_CLOSED', next, now, actorRole, reason),
    {
      ok: false,
      errorCode: reason,
      errorMessage:
        reason === 'PAGE_CHANGED'
          ? '当前页面版本已变化，草稿已失败关闭。'
          : '当前账号、连接或会话已变化，草稿已失败关闭。',
    },
  );
}

function roleDenied(
  draft: ReplyDraft,
  now: string,
  actorRole: ReplyActorRole,
): ReplyWorkflowResult {
  return result(
    draft,
    auditEvent('ROLE_DENIED', draft, now, actorRole, 'ROLE_NOT_ALLOWED'),
    {
      ok: false,
      errorCode: 'ROLE_NOT_ALLOWED',
      errorMessage: '只有 SUPPORT_AGENT 可以审核或请求发送回复。',
    },
  );
}

function validateDraftInput(input: CreateReplyDraftInput): string | null {
  if (
    !isValidContext(input.context) ||
    !isNonEmptyString(input.body) ||
    input.body.trim().length > XIANYU_REPLY_DRAFT_MAX_LENGTH ||
    !isIsoDate(input.now)
  ) {
    return '草稿内容、当前会话上下文或时间无效。';
  }
  if (input.context.source_page_version !== XIANYU_LOCAL_PAGE_VERSION) {
    return '当前页面版本未配置，不能创建回复草稿。';
  }
  if (Date.parse(input.context.detail_read_at) > Date.parse(input.now)) {
    return '会话详情读取时间晚于草稿创建时间。';
  }
  const ttl = input.ttl_ms ?? XIANYU_REPLY_DRAFT_DEFAULT_TTL_MS;
  if (
    !Number.isInteger(ttl) ||
    ttl <= 0 ||
    ttl > XIANYU_REPLY_DRAFT_MAX_TTL_MS
  ) {
    return '草稿有效期必须为正整数且不超过 15 分钟。';
  }
  if (input.draft_id !== undefined && !isNonEmptyString(input.draft_id)) {
    return '草稿标识无效。';
  }
  return null;
}

let cachedTabStorage: Storage | null | undefined;
let cachedTabRef: string | null = null;

function getOrCreateReplyTabRef(): string {
  if (typeof window === 'undefined') {
    throw new Error('当前回复工作流没有可确认的浏览器标签页');
  }
  const storage = window.sessionStorage;
  if (cachedTabStorage !== storage) {
    cachedTabStorage = storage;
    cachedTabRef = null;
  }
  if (cachedTabRef) return cachedTabRef;
  const stored = readLocalXianyuReplyTabRef();
  if (isNonEmptyString(stored)) {
    return stored;
  }
  const created = createOpaqueId('reply-tab');
  storage.setItem(XIANYU_REPLY_TAB_REF_STORAGE_KEY, created);
  cachedTabRef = created;
  return created;
}

export function readLocalXianyuReplyTabRef(): string | null {
  if (typeof window === 'undefined') return null;
  const storage = window.sessionStorage;
  if (cachedTabStorage !== storage) {
    cachedTabStorage = storage;
    cachedTabRef = null;
  }
  const stored = storage.getItem(XIANYU_REPLY_TAB_REF_STORAGE_KEY);
  cachedTabRef = isNonEmptyString(stored) ? stored : null;
  return cachedTabRef;
}

export function clearLocalXianyuReplyTabRef(): void {
  if (typeof window !== 'undefined') {
    window.sessionStorage.removeItem(XIANYU_REPLY_TAB_REF_STORAGE_KEY);
    cachedTabStorage = window.sessionStorage;
    cachedTabRef = null;
  }
}

export function createReplyContext(
  connection: XianyuLocalConnection,
  conversationId: string,
  sourcePageVersion: string,
  detailReadAt: string,
): ReplyContext {
  if (
    connection.provider !== 'XIANYU' ||
    connection.source_page !== 'LOCAL_FIXED_PAGE' ||
    connection.source_page_version !== XIANYU_LOCAL_PAGE_VERSION ||
    connection.status !== 'CONNECTED' ||
    sourcePageVersion !== XIANYU_LOCAL_PAGE_VERSION ||
    !isNonEmptyString(conversationId) ||
    !isIsoDate(detailReadAt)
  ) {
    throw new Error('当前闲鱼连接、会话或页面证据无法确认');
  }
  const tabRef = getOrCreateReplyTabRef();
  return {
    tab_ref: tabRef,
    connection_ref: connection.connection_id,
    account_ref: connection.display_identifier,
    conversation_ref: conversationId,
    source_page_version: sourcePageVersion,
    detail_read_at: detailReadAt,
  };
}

export function createReplyDraft(
  input: CreateReplyDraftInput,
): ReplyWorkflowResult {
  const validationError = validateDraftInput(input);
  if (validationError) return invalidInput(input.now, validationError);
  const ttl = input.ttl_ms ?? XIANYU_REPLY_DRAFT_DEFAULT_TTL_MS;
  const body = input.body.trim();
  const draft: ReplyDraft = {
    schema_version: XIANYU_REPLY_WORKFLOW_SCHEMA_VERSION,
    draft_id: input.draft_id ?? createOpaqueId('reply-draft'),
    context: { ...input.context },
    body,
    created_at: input.now,
    expires_at: new Date(Date.parse(input.now) + ttl).toISOString(),
    status: 'DRAFTED',
    ...emptyDraftFields(),
  };
  return result(
    draft,
    auditEvent('DRAFT_CREATED', draft, input.now, 'SUPPORT_AGENT', null),
    {
      ok: true,
      userActionRequired: 'REVIEW',
    },
  );
}

export function approveReplyDraft(
  input: ApproveReplyDraftInput,
): ReplyWorkflowResult {
  const validatedDraft = parseReplyDraft(input.draft);
  if (!validatedDraft) {
    return invalidInput(input.now, '回复草稿结构无效，已失败关闭。');
  }
  if (!isIsoDate(input.now) || !isNonEmptyString(input.approval_action_id)) {
    return invalidInput(
      input.now,
      '审核时间或审核动作标识无效。',
      validatedDraft,
    );
  }
  if (!isValidContext(input.current_context)) {
    return failClosedContext(
      validatedDraft,
      input.now,
      input.actor_role,
      'CONTEXT_MISMATCH',
    );
  }
  if (input.actor_role !== 'SUPPORT_AGENT') {
    return roleDenied(validatedDraft, input.now, input.actor_role);
  }
  if (Date.parse(input.now) >= Date.parse(validatedDraft.expires_at)) {
    return expiredDraft(validatedDraft, input.now, input.actor_role);
  }
  if (!hasCurrentContext(input.current_context, validatedDraft)) {
    return failClosedContext(
      validatedDraft,
      input.now,
      input.actor_role,
      input.current_context.source_page_version !==
        validatedDraft.context.source_page_version
        ? 'PAGE_CHANGED'
        : 'CONTEXT_MISMATCH',
    );
  }
  if (validatedDraft.status === 'APPROVED') {
    if (validatedDraft.approval_action_id === input.approval_action_id) {
      return result(
        validatedDraft,
        auditEvent(
          'APPROVAL_REPLAYED',
          validatedDraft,
          input.now,
          input.actor_role,
          null,
        ),
        { ok: true, userActionRequired: 'NONE' },
      );
    }
    return result(
      validatedDraft,
      auditEvent(
        'INPUT_REJECTED',
        validatedDraft,
        input.now,
        input.actor_role,
        'ALREADY_APPROVED',
      ),
      {
        ok: false,
        errorCode: 'ALREADY_APPROVED',
        errorMessage: '该草稿已经审核通过，不能用新的审核动作重复覆盖。',
      },
    );
  }
  if (validatedDraft.status !== 'DRAFTED') {
    return result(
      validatedDraft,
      auditEvent(
        'INPUT_REJECTED',
        validatedDraft,
        input.now,
        input.actor_role,
        'INVALID_STATE',
      ),
      {
        ok: false,
        errorCode: 'INVALID_STATE',
        errorMessage: '当前草稿状态不能继续审核。',
      },
    );
  }
  const next: ReplyDraft = {
    ...validatedDraft,
    status: 'APPROVED',
    approved_by_role: input.actor_role,
    approved_at: input.now,
    approval_action_id: input.approval_action_id,
    failure_code: null,
  };
  return result(
    next,
    auditEvent('DRAFT_APPROVED', next, input.now, input.actor_role, null),
    { ok: true, userActionRequired: 'NONE' },
  );
}

export function rejectReplyDraft(
  input: RejectReplyDraftInput,
): ReplyWorkflowResult {
  const validatedDraft = parseReplyDraft(input.draft);
  if (!validatedDraft) {
    return invalidInput(input.now, '回复草稿结构无效，已失败关闭。');
  }
  if (!isIsoDate(input.now) || !isNonEmptyString(input.rejection_action_id)) {
    return invalidInput(
      input.now,
      '拒绝时间或拒绝动作标识无效。',
      validatedDraft,
    );
  }
  if (!isValidContext(input.current_context)) {
    return failClosedContext(
      validatedDraft,
      input.now,
      input.actor_role,
      'CONTEXT_MISMATCH',
    );
  }
  if (input.actor_role !== 'SUPPORT_AGENT') {
    return roleDenied(validatedDraft, input.now, input.actor_role);
  }
  if (Date.parse(input.now) >= Date.parse(validatedDraft.expires_at)) {
    return expiredDraft(validatedDraft, input.now, input.actor_role);
  }
  if (!hasCurrentContext(input.current_context, validatedDraft)) {
    return failClosedContext(
      validatedDraft,
      input.now,
      input.actor_role,
      input.current_context.source_page_version !==
        validatedDraft.context.source_page_version
        ? 'PAGE_CHANGED'
        : 'CONTEXT_MISMATCH',
    );
  }
  if (
    validatedDraft.status !== 'DRAFTED' &&
    validatedDraft.status !== 'APPROVED'
  ) {
    return result(
      validatedDraft,
      auditEvent(
        'INPUT_REJECTED',
        validatedDraft,
        input.now,
        input.actor_role,
        'INVALID_STATE',
      ),
      {
        ok: false,
        errorCode: 'INVALID_STATE',
        errorMessage: '当前草稿状态不能取消。',
      },
    );
  }
  const next: ReplyDraft = {
    ...validatedDraft,
    status: 'REJECTED',
    approved_by_role: null,
    approved_at: null,
    approval_action_id: null,
    send_action_id: null,
    send_requested_at: null,
    failure_code: 'DRAFT_REJECTED',
  };
  return result(
    next,
    auditEvent(
      'DRAFT_REJECTED',
      next,
      input.now,
      input.actor_role,
      'DRAFT_REJECTED',
    ),
    { ok: true, userActionRequired: 'NONE' },
  );
}

export function requestExplicitReplySend(
  input: ExplicitSendInput,
): ReplyWorkflowResult {
  const validatedDraft = parseReplyDraft(input.draft);
  if (!validatedDraft) {
    return invalidInput(input.now, '回复草稿结构无效，已失败关闭。');
  }
  if (!isIsoDate(input.now) || !isNonEmptyString(input.send_action_id)) {
    return invalidInput(
      input.now,
      '发送时间或发送动作标识无效。',
      validatedDraft,
    );
  }
  if (!isValidContext(input.current_context)) {
    return failClosedContext(
      validatedDraft,
      input.now,
      input.actor_role,
      'CONTEXT_MISMATCH',
    );
  }
  if (input.actor_role !== 'SUPPORT_AGENT') {
    return roleDenied(validatedDraft, input.now, input.actor_role);
  }
  if (Date.parse(input.now) >= Date.parse(validatedDraft.expires_at)) {
    return expiredDraft(validatedDraft, input.now, input.actor_role);
  }
  if (!hasCurrentContext(input.current_context, validatedDraft)) {
    return failClosedContext(
      validatedDraft,
      input.now,
      input.actor_role,
      input.current_context.source_page_version !==
        validatedDraft.context.source_page_version
        ? 'PAGE_CHANGED'
        : 'CONTEXT_MISMATCH',
    );
  }
  if (validatedDraft.status === 'SEND_BLOCKED_NOT_CONFIGURED') {
    if (validatedDraft.send_action_id === input.send_action_id) {
      return result(
        validatedDraft,
        auditEvent(
          'SEND_REPLAYED',
          validatedDraft,
          input.now,
          input.actor_role,
          'NOT_CONFIGURED',
        ),
        {
          ok: false,
          errorCode: 'NOT_CONFIGURED',
          errorMessage: '真实平台发送适配器未配置；请在官方前台由您手动发送。',
          userActionRequired: 'MANUAL_SEND_ON_OFFICIAL_PAGE',
        },
      );
    }
    return result(
      validatedDraft,
      auditEvent(
        'INPUT_REJECTED',
        validatedDraft,
        input.now,
        input.actor_role,
        'SEND_ALREADY_REQUESTED',
      ),
      {
        ok: false,
        errorCode: 'SEND_ALREADY_REQUESTED',
        errorMessage: '该草稿已经记录过发送请求，不能重复提交。',
        userActionRequired: 'MANUAL_SEND_ON_OFFICIAL_PAGE',
      },
    );
  }
  if (validatedDraft.status !== 'APPROVED') {
    return result(
      validatedDraft,
      auditEvent(
        'INPUT_REJECTED',
        validatedDraft,
        input.now,
        input.actor_role,
        'REVIEW_REQUIRED',
      ),
      {
        ok: false,
        errorCode: 'REVIEW_REQUIRED',
        errorMessage: '发送前必须先完成坐席审核。',
      },
    );
  }
  if (input.confirmation !== 'CONFIRM_SEND') {
    return result(
      validatedDraft,
      auditEvent(
        'CONFIRMATION_REQUIRED',
        validatedDraft,
        input.now,
        input.actor_role,
        'CONFIRMATION_REQUIRED',
      ),
      {
        ok: false,
        errorCode: 'CONFIRMATION_REQUIRED',
        errorMessage: '发送动作需要勾选二次确认。',
      },
    );
  }
  const next: ReplyDraft = {
    ...validatedDraft,
    status: 'SEND_BLOCKED_NOT_CONFIGURED',
    send_action_id: input.send_action_id,
    send_requested_at: input.now,
    failure_code: 'NOT_CONFIGURED',
  };
  return result(
    next,
    auditEvent(
      'SEND_BLOCKED_NOT_CONFIGURED',
      next,
      input.now,
      input.actor_role,
      'NOT_CONFIGURED',
    ),
    {
      ok: false,
      errorCode: 'NOT_CONFIGURED',
      errorMessage:
        '真实平台发送适配器未配置；本次没有发起网络请求，请在官方前台由您手动发送。',
      userActionRequired: 'MANUAL_SEND_ON_OFFICIAL_PAGE',
    },
  );
}

export class LocalHumanApprovedReplyWorkflow implements HumanApprovedReplyWorkflow {
  createDraft(input: CreateReplyDraftInput): ReplyWorkflowResult {
    return createReplyDraft(input);
  }

  approveDraft(input: ApproveReplyDraftInput): ReplyWorkflowResult {
    return approveReplyDraft(input);
  }

  rejectDraft(input: RejectReplyDraftInput): ReplyWorkflowResult {
    return rejectReplyDraft(input);
  }

  requestExplicitSend(input: ExplicitSendInput): ReplyWorkflowResult {
    return requestExplicitReplySend(input);
  }
}

function parseReplyContext(value: unknown): ReplyContext | null {
  return isValidContext(value) ? { ...value } : null;
}

function parseReplyDraft(value: unknown): ReplyDraft | null {
  if (!isRecord(value) || !hasExactFields(value, DRAFT_FIELDS)) return null;
  const context = parseReplyContext(value.context);
  if (
    value.schema_version !== XIANYU_REPLY_WORKFLOW_SCHEMA_VERSION ||
    !isNonEmptyString(value.draft_id) ||
    !context ||
    typeof value.body !== 'string' ||
    value.body.trim().length === 0 ||
    value.body.length > XIANYU_REPLY_DRAFT_MAX_LENGTH ||
    !isIsoDate(value.created_at) ||
    !isIsoDate(value.expires_at) ||
    !validTimestampOrder(
      value.created_at as string,
      value.expires_at as string,
    ) ||
    !isReplyStatus(value.status) ||
    (value.approved_by_role !== null &&
      !isReplyActorRole(value.approved_by_role)) ||
    (value.approved_at !== null && !isIsoDate(value.approved_at)) ||
    (value.approval_action_id !== null &&
      !isNonEmptyString(value.approval_action_id)) ||
    (value.send_action_id !== null &&
      !isNonEmptyString(value.send_action_id)) ||
    (value.send_requested_at !== null && !isIsoDate(value.send_requested_at)) ||
    (value.failure_code !== null && !isReplyFailureCode(value.failure_code))
  ) {
    return null;
  }
  const draft = {
    ...(value as Omit<ReplyDraft, 'context'>),
    context,
  } as ReplyDraft;
  const hasApproval =
    draft.approved_by_role !== null ||
    draft.approved_at !== null ||
    draft.approval_action_id !== null;
  const hasSendRequest =
    draft.send_action_id !== null || draft.send_requested_at !== null;
  if (
    (draft.approved_at !== null &&
      (!validTimestampOrder(draft.created_at, draft.approved_at) ||
        Date.parse(draft.approved_at) >= Date.parse(draft.expires_at))) ||
    (draft.send_requested_at !== null &&
      (!draft.approved_at ||
        !validTimestampOrder(draft.approved_at, draft.send_requested_at) ||
        Date.parse(draft.send_requested_at) >= Date.parse(draft.expires_at)))
  ) {
    return null;
  }
  if (
    draft.status === 'DRAFTED' &&
    (hasApproval || hasSendRequest || draft.failure_code !== null)
  ) {
    return null;
  }
  if (
    draft.status === 'APPROVED' &&
    (draft.approved_by_role !== 'SUPPORT_AGENT' ||
      draft.approved_at === null ||
      draft.approval_action_id === null ||
      hasSendRequest ||
      draft.failure_code !== null)
  ) {
    return null;
  }
  if (
    draft.status === 'SEND_BLOCKED_NOT_CONFIGURED' &&
    (draft.approved_by_role !== 'SUPPORT_AGENT' ||
      draft.approved_at === null ||
      draft.approval_action_id === null ||
      draft.send_action_id === null ||
      draft.send_requested_at === null ||
      draft.failure_code !== 'NOT_CONFIGURED')
  ) {
    return null;
  }
  if (draft.status === 'EXPIRED' && draft.failure_code !== 'DRAFT_EXPIRED')
    return null;
  if (draft.status === 'EXPIRED' && (hasApproval || hasSendRequest)) {
    return null;
  }
  if (
    draft.status === 'REJECTED' &&
    (draft.failure_code !== 'DRAFT_REJECTED' || hasApproval || hasSendRequest)
  ) {
    return null;
  }
  if (
    draft.status === 'FAILED_CLOSED' &&
    ((draft.failure_code !== 'CONTEXT_MISMATCH' &&
      draft.failure_code !== 'PAGE_CHANGED') ||
      hasApproval ||
      hasSendRequest)
  ) {
    return null;
  }
  return draft;
}

function parseReplyAuditEvent(value: unknown): ReplyAuditEvent | null {
  if (!isRecord(value) || !hasExactFields(value, AUDIT_FIELDS)) return null;
  if (
    value.schema_version !== XIANYU_REPLY_WORKFLOW_SCHEMA_VERSION ||
    !isNonEmptyString(value.event_id) ||
    !isReplyEventType(value.event_type) ||
    !isNonEmptyString(value.draft_id) ||
    !isNonEmptyString(value.connection_ref) ||
    !isNonEmptyString(value.account_ref) ||
    !isNonEmptyString(value.conversation_ref) ||
    !isReplyActorRole(value.actor_role) ||
    !isIsoDate(value.occurred_at) ||
    (value.reason !== null && !isReplyFailureCode(value.reason)) ||
    typeof value.body_length !== 'number' ||
    !Number.isInteger(value.body_length) ||
    value.body_length < 0 ||
    value.body_length > XIANYU_REPLY_DRAFT_MAX_LENGTH
  ) {
    return null;
  }
  return value as ReplyAuditEvent;
}

function auditEventMatchesDraft(
  event: ReplyAuditEvent,
  draft: ReplyDraft,
): boolean {
  return (
    event.draft_id === draft.draft_id &&
    event.connection_ref === draft.context.connection_ref &&
    event.account_ref === draft.context.account_ref &&
    event.conversation_ref === draft.context.conversation_ref &&
    event.body_length === draft.body.length
  );
}

export function parseReplyWorkflowSnapshot(
  raw: string | null,
): ReplyWorkflowSnapshot | null {
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (
      !isRecord(parsed) ||
      !hasExactFields(parsed, SNAPSHOT_FIELDS) ||
      parsed.schema_version !== XIANYU_REPLY_WORKFLOW_SCHEMA_VERSION ||
      !Array.isArray(parsed.audit_events) ||
      parsed.audit_events.length === 0 ||
      parsed.audit_events.length > XIANYU_REPLY_AUDIT_MAX_EVENTS
    ) {
      return null;
    }
    const draft = parseReplyDraft(parsed.draft);
    const auditEvents = parsed.audit_events.map(parseReplyAuditEvent);
    if (!draft || auditEvents.some((event) => event === null)) return null;
    const normalizedAuditEvents = auditEvents as ReplyAuditEvent[];
    if (
      normalizedAuditEvents.some(
        (event) => !auditEventMatchesDraft(event, draft),
      )
    ) {
      return null;
    }
    return {
      schema_version: XIANYU_REPLY_WORKFLOW_SCHEMA_VERSION,
      draft,
      audit_events: normalizedAuditEvents,
    };
  } catch {
    return null;
  }
}

export function appendReplyWorkflowResult(
  previous: ReplyWorkflowSnapshot | null,
  workflowResult: ReplyWorkflowResult,
): ReplyWorkflowSnapshot | null {
  if (
    !workflowResult.draft ||
    !parseReplyDraft(workflowResult.draft) ||
    !parseReplyAuditEvent(workflowResult.audit_event) ||
    !auditEventMatchesDraft(workflowResult.audit_event, workflowResult.draft)
  ) {
    return null;
  }
  const parsedPrevious = previous
    ? parseReplyWorkflowSnapshot(JSON.stringify(previous))
    : null;
  const canReusePrevious =
    parsedPrevious !== null &&
    parsedPrevious.draft.draft_id === workflowResult.draft.draft_id &&
    sameContext(parsedPrevious.draft.context, workflowResult.draft.context);
  const auditEvents = [
    ...(canReusePrevious ? parsedPrevious.audit_events : []),
    workflowResult.audit_event,
  ].slice(-XIANYU_REPLY_AUDIT_MAX_EVENTS);
  return {
    schema_version: XIANYU_REPLY_WORKFLOW_SCHEMA_VERSION,
    draft: workflowResult.draft,
    audit_events: auditEvents,
  };
}

type ReplyWorkflowListener = () => void;
const listeners = new Set<ReplyWorkflowListener>();
let cachedStorage: Storage | null | undefined;
let cachedRaw: string | null | undefined;
let cachedSnapshot: ReplyWorkflowSnapshot | null = null;

export function readStoredLocalXianyuReplyWorkflow(): ReplyWorkflowSnapshot | null {
  if (typeof window === 'undefined') return null;
  const storage = window.sessionStorage;
  if (cachedStorage !== storage) {
    cachedStorage = storage;
    cachedRaw = undefined;
    cachedSnapshot = null;
  }
  const raw = storage.getItem(XIANYU_REPLY_WORKFLOW_STORAGE_KEY);
  if (raw === cachedRaw) return cachedSnapshot;
  const snapshot = parseReplyWorkflowSnapshot(raw);
  if (!snapshot && raw !== null) {
    storage.removeItem(XIANYU_REPLY_WORKFLOW_STORAGE_KEY);
  }
  cachedRaw = snapshot ? raw : null;
  cachedSnapshot = snapshot;
  return snapshot;
}

export function writeLocalXianyuReplyWorkflow(
  snapshot: ReplyWorkflowSnapshot,
): void {
  const parsed = parseReplyWorkflowSnapshot(JSON.stringify(snapshot));
  if (!parsed) throw new Error('回复工作流结果不符合本地白名单结构');
  const serialized = JSON.stringify(parsed);
  window.sessionStorage.setItem(XIANYU_REPLY_WORKFLOW_STORAGE_KEY, serialized);
  cachedStorage = window.sessionStorage;
  cachedRaw = serialized;
  cachedSnapshot = parsed;
  listeners.forEach((listener) => listener());
}

export function clearLocalXianyuReplyWorkflow(): void {
  if (typeof window !== 'undefined') {
    window.sessionStorage.removeItem(XIANYU_REPLY_WORKFLOW_STORAGE_KEY);
    cachedStorage = window.sessionStorage;
    cachedRaw = null;
    cachedSnapshot = null;
    listeners.forEach((listener) => listener());
  }
}

export function subscribeLocalXianyuReplyWorkflow(
  listener: ReplyWorkflowListener,
): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
