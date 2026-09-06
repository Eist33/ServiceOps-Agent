/**
 * Shared protocol for the Chrome/Edge Manifest V3 bridge.
 *
 * This file intentionally contains only pure validation and data shaping. It
 * never reaches the network, reads cookies, or receives credentials. The
 * service worker and the workbench page both treat this protocol as
 * untrusted input and fail closed on every unknown field.
 */

export const PROTOCOL_VERSION = 1;
export const BRIDGE_MODE = 'USER_CONTROLLED';
export const ADAPTER_STATE = 'NOT_CONFIGURED';
// Reuse the existing fixed-page fixture version so the local workbench can
// compare bridge context without accepting an unknown real-page version.
export const LOCAL_VISIBLE_PAGE_VERSION = 'local-fixed-page-v1';
export const UNVERIFIED_OFFICIAL_PAGE_VERSION = 'unverified-official-page';
export const MAX_DRAFT_LENGTH = 2_000;
export const MAX_MESSAGE_COUNT = 50;
export const MAX_MESSAGE_LENGTH = 2_000;
export const DRAFT_DEFAULT_TTL_MS = 10 * 60 * 1_000;
export const DRAFT_MAX_TTL_MS = 15 * 60 * 1_000;
export const SELECTION_TTL_MS = 5 * 60 * 1_000;
export const MAX_AUDIT_EVENTS = 50;

export const MESSAGE_TYPES = Object.freeze({
  GET_STATE: 'GET_STATE',
  READ_CURRENT_VISIBLE_SESSION: 'READ_CURRENT_VISIBLE_SESSION',
  CREATE_DRAFT: 'CREATE_DRAFT',
  APPROVE_DRAFT: 'APPROVE_DRAFT',
  REVOKE_DRAFT: 'REVOKE_DRAFT',
  RECORD_SEND_INTENT: 'RECORD_SEND_INTENT',
  OPEN_WORKBENCH: 'OPEN_WORKBENCH',
  PUSH_DRAFT_TO_WORKBENCH: 'PUSH_DRAFT_TO_WORKBENCH',
  READ_VISIBLE_SESSION: 'READ_VISIBLE_SESSION',
  DELIVER_DRAFT_TO_WORKBENCH: 'DELIVER_DRAFT_TO_WORKBENCH',
});

export const PAGE_KINDS = Object.freeze({
  OFFICIAL_VISIBLE_PAGE: 'OFFICIAL_VISIBLE_PAGE',
  LOCAL_FIXED_PAGE: 'LOCAL_FIXED_PAGE',
});

const SENSITIVE_INPUT_PATTERN =
  /(验证码|短信验证码|password|passwd|cookie|token|access[_-]?token|authorization|bearer)/i;

const IDENTIFIER_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;

function isRecord(value) {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function hasExactKeys(value, keys) {
  if (!isRecord(value)) return false;
  const actual = Object.keys(value);
  return (
    actual.length === keys.length &&
    keys.every((key) => Object.prototype.hasOwnProperty.call(value, key))
  );
}

function isNonEmptyString(value, max = 512) {
  return typeof value === 'string' && value.trim().length > 0 && value.length <= max;
}

function isIsoDate(value) {
  return typeof value === 'string' && Number.isFinite(Date.parse(value));
}

function isIdentifier(value) {
  return typeof value === 'string' && IDENTIFIER_PATTERN.test(value);
}

function isSafeVisibleText(value, max = MAX_MESSAGE_LENGTH) {
  return typeof value === 'string' && value.length <= max && !SENSITIVE_INPUT_PATTERN.test(value);
}

export function containsSensitiveInput(value) {
  return typeof value === 'string' && SENSITIVE_INPUT_PATTERN.test(value);
}

export function createOpaqueId(prefix) {
  const uuid = globalThis.crypto?.randomUUID?.();
  return `${prefix}-${uuid ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`}`;
}

export function createRequest(type, payload = {}) {
  if (!Object.values(MESSAGE_TYPES).includes(type)) {
    throw new Error('未知扩展消息类型');
  }
  return {
    protocol_version: PROTOCOL_VERSION,
    type,
    request_id: createOpaqueId('bridge-request'),
    payload,
  };
}

export function parseRequest(value) {
  if (
    !hasExactKeys(value, ['protocol_version', 'type', 'request_id', 'payload']) ||
    value.protocol_version !== PROTOCOL_VERSION ||
    !Object.values(MESSAGE_TYPES).includes(value.type) ||
    !isNonEmptyString(value.request_id, 256) ||
    !isRecord(value.payload)
  ) {
    return null;
  }
  return value;
}

function baseContextFields(value) {
  return (
    isIdentifier(value.tab_ref) &&
    isIdentifier(value.connection_ref) &&
    isIdentifier(value.account_ref) &&
    isIdentifier(value.conversation_ref) &&
    isNonEmptyString(value.source_page_version, 128) &&
    isIsoDate(value.detail_read_at)
  );
}

export function parseVisibleSessionSnapshot(value) {
  const fields = [
    'schema_version',
    'mode',
    'adapter_state',
    'provider',
    'external_requests_enabled',
    'tab_ref',
    'connection_ref',
    'account_ref',
    'conversation_ref',
    'source_page_version',
    'selected_at',
    'detail_read_at',
    'messages',
  ];
  if (
    !hasExactKeys(value, fields) ||
    value.schema_version !== PROTOCOL_VERSION ||
    value.mode !== BRIDGE_MODE ||
    value.adapter_state !== ADAPTER_STATE ||
    value.provider !== 'XIANYU' ||
    value.external_requests_enabled !== false ||
    !baseContextFields(value) ||
    !isIsoDate(value.selected_at) ||
    !Array.isArray(value.messages) ||
    value.messages.length > MAX_MESSAGE_COUNT
  ) {
    return null;
  }
  if (value.source_page_version !== LOCAL_VISIBLE_PAGE_VERSION) return null;
  const messages = value.messages.map((message) => parseVisibleMessage(message));
  if (messages.some((message) => message === null)) return null;
  return { ...value, messages };
}

export function parseVisibleMessage(value) {
  const fields = ['message_id', 'sender', 'text', 'sent_at'];
  if (
    !hasExactKeys(value, fields) ||
    !isIdentifier(value.message_id) ||
    !['SELF', 'OTHER', 'SYSTEM', 'UNKNOWN'].includes(value.sender) ||
    !isSafeVisibleText(value.text, MAX_MESSAGE_LENGTH) ||
    (value.sent_at !== null && !isIsoDate(value.sent_at))
  ) {
    return null;
  }
  return { ...value };
}

export function parseDraft(value) {
  const fields = [
    'schema_version',
    'draft_id',
    'mode',
    'adapter_state',
    'external_requests_enabled',
    'context',
    'body',
    'created_at',
    'expires_at',
    'status',
    'approved_at',
    'approval_action_id',
    'revoke_action_id',
    'send_action_id',
    'send_requested_at',
    'failure_code',
  ];
  if (
    !hasExactKeys(value, fields) ||
    value.schema_version !== PROTOCOL_VERSION ||
    !isIdentifier(value.draft_id) ||
    value.mode !== BRIDGE_MODE ||
    value.adapter_state !== ADAPTER_STATE ||
    value.external_requests_enabled !== false ||
    !isNonEmptyString(value.body, MAX_DRAFT_LENGTH) ||
    value.body.trim().length === 0 ||
    !isIsoDate(value.created_at) ||
    !isIsoDate(value.expires_at) ||
    Date.parse(value.expires_at) <= Date.parse(value.created_at) ||
    !['DRAFTED', 'APPROVED', 'SEND_BLOCKED_NOT_CONFIGURED', 'REVOKED', 'EXPIRED', 'FAILED_CLOSED'].includes(value.status) ||
    (value.approved_at !== null && !isIsoDate(value.approved_at)) ||
    (value.approval_action_id !== null && !isIdentifier(value.approval_action_id)) ||
    (value.revoke_action_id !== null && !isIdentifier(value.revoke_action_id)) ||
    (value.send_action_id !== null && !isIdentifier(value.send_action_id)) ||
    (value.send_requested_at !== null && !isIsoDate(value.send_requested_at)) ||
    (value.failure_code !== null && !isNonEmptyString(value.failure_code, 128))
  ) {
    return null;
  }
  const context = parseContext(value.context);
  if (!context) return null;
  if (
    value.approved_at !== null &&
    (Date.parse(value.approved_at) < Date.parse(value.created_at) ||
      Date.parse(value.approved_at) >= Date.parse(value.expires_at))
  ) {
    return null;
  }
  if (
    value.send_requested_at !== null &&
    (value.approved_at === null ||
      Date.parse(value.send_requested_at) < Date.parse(value.approved_at) ||
      Date.parse(value.send_requested_at) >= Date.parse(value.expires_at))
  ) {
    return null;
  }
  return { ...value, context };
}

export function parseContext(value) {
  if (
    !hasExactKeys(value, [
      'tab_ref',
      'connection_ref',
      'account_ref',
      'conversation_ref',
      'source_page_version',
      'detail_read_at',
    ]) ||
    !baseContextFields(value)
  ) {
    return null;
  }
  return { ...value };
}

export function parseAuditEvent(value) {
  const fields = [
    'schema_version',
    'event_id',
    'event_type',
    'draft_id',
    'occurred_at',
    'reason',
  ];
  if (
    !hasExactKeys(value, fields) ||
    value.schema_version !== PROTOCOL_VERSION ||
    !isIdentifier(value.event_id) ||
    ![
      'DRAFT_CREATED',
      'DRAFT_APPROVED',
      'APPROVAL_REPLAYED',
      'DRAFT_REVOKED',
      'SEND_BLOCKED_NOT_CONFIGURED',
      'SEND_REPLAYED',
      'DRAFT_EXPIRED',
      'FAILED_CLOSED',
      'INPUT_REJECTED',
    ].includes(value.event_type) ||
    !isIdentifier(value.draft_id) ||
    !isIsoDate(value.occurred_at) ||
    (value.reason !== null && !isNonEmptyString(value.reason, 128))
  ) {
    return null;
  }
  return { ...value };
}

export function parseWorkflowSnapshot(value) {
  const fields = ['schema_version', 'visible_session', 'draft', 'audit_events'];
  if (
    !hasExactKeys(value, fields) ||
    value.schema_version !== PROTOCOL_VERSION ||
    !Array.isArray(value.audit_events) ||
    value.audit_events.length === 0 ||
    value.audit_events.length > MAX_AUDIT_EVENTS
  ) {
    return null;
  }
  const visibleSession = parseVisibleSessionSnapshot(value.visible_session);
  const draft = parseDraft(value.draft);
  const auditEvents = value.audit_events.map(parseAuditEvent);
  if (!visibleSession || !draft || auditEvents.some((event) => event === null)) {
    return null;
  }
  if (!contextsEqual(contextFromSnapshot(visibleSession), draft.context)) {
    return null;
  }
  if (auditEvents.some((event) => event.draft_id !== draft.draft_id)) {
    return null;
  }
  return { ...value, visible_session: visibleSession, draft, audit_events: auditEvents };
}

export function makeVisibleSessionSnapshot({
  tabRef,
  connectionRef,
  accountRef,
  conversationRef,
  selectedAt,
  detailReadAt,
  messages,
}) {
  const snapshot = {
    schema_version: PROTOCOL_VERSION,
    mode: BRIDGE_MODE,
    adapter_state: ADAPTER_STATE,
    provider: 'XIANYU',
    external_requests_enabled: false,
    tab_ref: tabRef,
    connection_ref: connectionRef,
    account_ref: accountRef,
    conversation_ref: conversationRef,
    source_page_version: LOCAL_VISIBLE_PAGE_VERSION,
    selected_at: selectedAt,
    detail_read_at: detailReadAt,
    messages,
  };
  return parseVisibleSessionSnapshot(snapshot);
}

export function createAuditEvent(eventType, draftId, occurredAt, reason = null) {
  return {
    schema_version: PROTOCOL_VERSION,
    event_id: createOpaqueId('bridge-audit'),
    event_type: eventType,
    draft_id: draftId,
    occurred_at: occurredAt,
    reason,
  };
}

export function contextsEqual(left, right) {
  const a = parseContext(left);
  const b = parseContext(right);
  return Boolean(
    a &&
      b &&
      a.tab_ref === b.tab_ref &&
      a.connection_ref === b.connection_ref &&
      a.account_ref === b.account_ref &&
      a.conversation_ref === b.conversation_ref &&
      a.source_page_version === b.source_page_version &&
      a.detail_read_at === b.detail_read_at,
  );
}

export function contextFromSnapshot(snapshot) {
  const parsed = parseVisibleSessionSnapshot(snapshot);
  if (!parsed) return null;
  return {
    tab_ref: parsed.tab_ref,
    connection_ref: parsed.connection_ref,
    account_ref: parsed.account_ref,
    conversation_ref: parsed.conversation_ref,
    source_page_version: parsed.source_page_version,
    detail_read_at: parsed.detail_read_at,
  };
}

export function selectionIsFresh(snapshot, now) {
  const parsed = parseVisibleSessionSnapshot(snapshot);
  if (!parsed || !isIsoDate(now)) return false;
  const age = Date.parse(now) - Date.parse(parsed.selected_at);
  return age >= 0 && age < SELECTION_TTL_MS;
}

export function sanitizeBridgePayload(value) {
  if (!isRecord(value) || containsSensitiveInput(JSON.stringify(value))) return null;
  const draft = parseDraft(value.draft);
  if (!draft) return null;
  return {
    protocol_version: PROTOCOL_VERSION,
    kind: 'XIANYU_DRAFT_BRIDGE',
    mode: BRIDGE_MODE,
    adapter_state: ADAPTER_STATE,
    external_requests_enabled: false,
    draft,
  };
}
