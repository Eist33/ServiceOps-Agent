/**
 * Browser-extension -> local workbench message boundary.
 *
 * The extension can only deliver an untrusted, local draft preview. The
 * workbench must still require an explicit click and rebuild its own current
 * reply context before creating a draft. This parser never accepts a token,
 * cookie, password, verification code, or transport handle.
 */

export type XianyuExtensionDraft = {
  schema_version: 1;
  draft_id: string;
  mode: 'USER_CONTROLLED';
  adapter_state: 'NOT_CONFIGURED';
  external_requests_enabled: false;
  context: {
    tab_ref: string;
    connection_ref: string;
    account_ref: string;
    conversation_ref: string;
    source_page_version: string;
    detail_read_at: string;
  };
  body: string;
  created_at: string;
  expires_at: string;
  status:
    | 'DRAFTED'
    | 'APPROVED'
    | 'SEND_BLOCKED_NOT_CONFIGURED'
    | 'REVOKED'
    | 'EXPIRED'
    | 'FAILED_CLOSED';
  approved_at: string | null;
  approval_action_id: string | null;
  revoke_action_id: string | null;
  send_action_id: string | null;
  send_requested_at: string | null;
  failure_code: string | null;
};

export type XianyuExtensionDraftEnvelope = {
  protocol_version: 1;
  kind: 'XIANYU_DRAFT_BRIDGE';
  mode: 'USER_CONTROLLED';
  adapter_state: 'NOT_CONFIGURED';
  external_requests_enabled: false;
  draft: XianyuExtensionDraft;
};

const DRAFT_FIELDS = [
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
] as const;
const CONTEXT_FIELDS = [
  'tab_ref',
  'connection_ref',
  'account_ref',
  'conversation_ref',
  'source_page_version',
  'detail_read_at',
] as const;
const ENVELOPE_FIELDS = [
  'protocol_version',
  'kind',
  'mode',
  'adapter_state',
  'external_requests_enabled',
  'draft',
] as const;
const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const SENSITIVE_INPUT =
  /(验证码|短信验证码|password|passwd|cookie|token|access[_-]?token|authorization|bearer)/i;
const STATUSES = [
  'DRAFTED',
  'APPROVED',
  'SEND_BLOCKED_NOT_CONFIGURED',
  'REVOKED',
  'EXPIRED',
  'FAILED_CLOSED',
] as const;

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

function isIdentifier(value: unknown): value is string {
  return typeof value === 'string' && IDENTIFIER.test(value);
}

function nullableIdentifier(value: unknown): value is string | null {
  return value === null || isIdentifier(value);
}

function parseContext(value: unknown): XianyuExtensionDraft['context'] | null {
  if (!isRecord(value) || !hasExactFields(value, CONTEXT_FIELDS)) return null;
  if (
    !isIdentifier(value.tab_ref) ||
    !isIdentifier(value.connection_ref) ||
    !isIdentifier(value.account_ref) ||
    !isIdentifier(value.conversation_ref) ||
    typeof value.source_page_version !== 'string' ||
    value.source_page_version.length > 128 ||
    !isIsoDate(value.detail_read_at)
  ) {
    return null;
  }
  return value as XianyuExtensionDraft['context'];
}

function parseDraft(value: unknown): XianyuExtensionDraft | null {
  if (!isRecord(value) || !hasExactFields(value, DRAFT_FIELDS)) return null;
  const context = parseContext(value.context);
  if (
    value.schema_version !== 1 ||
    !isIdentifier(value.draft_id) ||
    value.mode !== 'USER_CONTROLLED' ||
    value.adapter_state !== 'NOT_CONFIGURED' ||
    value.external_requests_enabled !== false ||
    !context ||
    typeof value.body !== 'string' ||
    value.body.trim().length === 0 ||
    value.body.length > 2_000 ||
    SENSITIVE_INPUT.test(value.body) ||
    !isIsoDate(value.created_at) ||
    !isIsoDate(value.expires_at) ||
    Date.parse(value.expires_at) <= Date.parse(value.created_at) ||
    !STATUSES.includes(value.status as XianyuExtensionDraft['status']) ||
    (value.approved_at !== null && !isIsoDate(value.approved_at)) ||
    !nullableIdentifier(value.approval_action_id) ||
    !nullableIdentifier(value.revoke_action_id) ||
    !nullableIdentifier(value.send_action_id) ||
    (value.send_requested_at !== null && !isIsoDate(value.send_requested_at)) ||
    (value.failure_code !== null && !isIdentifier(value.failure_code))
  ) {
    return null;
  }
  return { ...(value as XianyuExtensionDraft), context };
}

export function parseXianyuExtensionDraftMessage(
  value: unknown,
): XianyuExtensionDraftEnvelope | null {
  if (!isRecord(value) || !hasExactFields(value, ENVELOPE_FIELDS)) return null;
  if (
    value.protocol_version !== 1 ||
    value.kind !== 'XIANYU_DRAFT_BRIDGE' ||
    value.mode !== 'USER_CONTROLLED' ||
    value.adapter_state !== 'NOT_CONFIGURED' ||
    value.external_requests_enabled !== false
  ) {
    return null;
  }
  const draft = parseDraft(value.draft);
  if (!draft) return null;
  return {
    protocol_version: 1,
    kind: 'XIANYU_DRAFT_BRIDGE',
    mode: 'USER_CONTROLLED',
    adapter_state: 'NOT_CONFIGURED',
    external_requests_enabled: false,
    draft,
  };
}

export function isCurrentXianyuExtensionContext(
  envelope: XianyuExtensionDraftEnvelope,
  context: XianyuExtensionDraft['context'],
): boolean {
  const parsed = parseXianyuExtensionDraftMessage(envelope);
  return Boolean(
    parsed &&
      parsed.draft.context.tab_ref === context.tab_ref &&
      parsed.draft.context.connection_ref === context.connection_ref &&
      parsed.draft.context.account_ref === context.account_ref &&
      parsed.draft.context.conversation_ref === context.conversation_ref &&
      parsed.draft.context.source_page_version === context.source_page_version &&
      parsed.draft.context.detail_read_at === context.detail_read_at,
  );
}
