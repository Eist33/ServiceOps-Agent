import {
  ADAPTER_STATE,
  BRIDGE_MODE,
  DRAFT_DEFAULT_TTL_MS,
  DRAFT_MAX_TTL_MS,
  MAX_AUDIT_EVENTS,
  MAX_DRAFT_LENGTH,
  createAuditEvent,
  createOpaqueId,
  contextFromSnapshot,
  contextsEqual,
  parseContext,
  parseDraft,
  parseVisibleSessionSnapshot,
  parseWorkflowSnapshot,
  selectionIsFresh,
} from './protocol.js';

const ALLOWED_ACTOR_ROLE = 'SUPPORT_AGENT';

function isIsoDate(value) {
  return typeof value === 'string' && Number.isFinite(Date.parse(value));
}

function isNonEmptyString(value, max = 256) {
  return typeof value === 'string' && value.trim().length > 0 && value.length <= max;
}

function sameOrNull(left, right) {
  return left === right || (left === null && right === null);
}

function stateFields() {
  return {
    approved_at: null,
    approval_action_id: null,
    revoke_action_id: null,
    send_action_id: null,
    send_requested_at: null,
    failure_code: null,
  };
}

function contextMatchesSnapshot(currentSnapshot, draft) {
  const current = contextFromSnapshot(currentSnapshot);
  return Boolean(current && contextsEqual(current, draft.context));
}

function eventFor(type, draft, now, reason = null) {
  return createAuditEvent(type, draft?.draft_id ?? 'unknown-draft', now, reason);
}

function workflowResult(draft, auditEvent, options = {}) {
  return {
    ok: options.ok ?? false,
    status: draft?.status ?? 'NO_DRAFT',
    draft: draft ?? null,
    audit_event: auditEvent,
    error_code: options.error_code ?? null,
    error_message: options.error_message ?? null,
    external_request_started: false,
    sent: false,
    user_action_required: options.user_action_required ?? 'NONE',
  };
}

function invalidInput(now, message, draft = null, reason = 'INVALID_INPUT') {
  return workflowResult(draft, eventFor('INPUT_REJECTED', draft, now, reason), {
    error_code: reason,
    error_message: message,
  });
}

function failClosed(draft, now, reason, message) {
  const next = {
    ...draft,
    status: 'FAILED_CLOSED',
    approved_at: null,
    approval_action_id: null,
    revoke_action_id: null,
    send_action_id: null,
    send_requested_at: null,
    failure_code: reason,
  };
  return workflowResult(next, eventFor('FAILED_CLOSED', next, now, reason), {
    error_code: reason,
    error_message: message,
  });
}

function expireDraft(draft, now) {
  const next = {
    ...draft,
    status: 'EXPIRED',
    approved_at: null,
    approval_action_id: null,
    revoke_action_id: null,
    send_action_id: null,
    send_requested_at: null,
    failure_code: 'DRAFT_EXPIRED',
  };
  return workflowResult(next, eventFor('DRAFT_EXPIRED', next, now, 'DRAFT_EXPIRED'), {
    error_code: 'DRAFT_EXPIRED',
    error_message: '本地回复草稿已过期，已失败关闭；请重新读取当前会话。',
  });
}

function guardAction({ draft, currentSnapshot, now }) {
  const parsedDraft = parseDraft(draft);
  if (!parsedDraft) {
    return invalidInput(now, '本地草稿结构无效，已失败关闭。');
  }
  if (!isIsoDate(now)) {
    return invalidInput(now, '当前时间无效。', parsedDraft);
  }
  if (!parseVisibleSessionSnapshot(currentSnapshot)) {
    return failClosed(
      parsedDraft,
      now,
      'CONTEXT_MISMATCH',
      '当前可见会话上下文无法确认，草稿已失败关闭。',
    );
  }
  if (!selectionIsFresh(currentSnapshot, now)) {
    return failClosed(
      parsedDraft,
      now,
      'PAGE_CHANGED',
      '当前可见页面选择已过期，草稿已失败关闭。',
    );
  }
  if (Date.parse(now) >= Date.parse(parsedDraft.expires_at)) {
    return expireDraft(parsedDraft, now);
  }
  if (!contextMatchesSnapshot(currentSnapshot, parsedDraft)) {
    return failClosed(
      parsedDraft,
      now,
      'CONTEXT_MISMATCH',
      '当前标签页、账号、连接或会话已变化，草稿已失败关闭。',
    );
  }
  return null;
}

function validateActionId(actionId, label) {
  return isNonEmptyString(actionId, 256)
    ? null
    : invalidInput(new Date().toISOString(), `${label}动作标识无效。`);
}

export function createDraft({
  snapshot,
  body,
  now,
  ttlMs = DRAFT_DEFAULT_TTL_MS,
  draftId = createOpaqueId('bridge-draft'),
}) {
  const parsedSnapshot = parseVisibleSessionSnapshot(snapshot);
  if (!parsedSnapshot || !isIsoDate(now)) {
    return invalidInput(now, '当前可见会话或时间无效，不能创建草稿。');
  }
  if (!selectionIsFresh(parsedSnapshot, now)) {
    return invalidInput(now, '当前可见页面选择已过期，请重新点击读取。');
  }
  if (
    !isNonEmptyString(body, MAX_DRAFT_LENGTH) ||
    body.trim().length === 0 ||
    !Number.isInteger(ttlMs) ||
    ttlMs <= 0 ||
    ttlMs > DRAFT_MAX_TTL_MS ||
    !isNonEmptyString(draftId, 256)
  ) {
    return invalidInput(now, '草稿正文、有效期或草稿标识无效。');
  }
  const draft = {
    schema_version: 1,
    draft_id: draftId,
    mode: BRIDGE_MODE,
    adapter_state: ADAPTER_STATE,
    external_requests_enabled: false,
    context: contextFromSnapshot(parsedSnapshot),
    body: body.trim(),
    created_at: now,
    expires_at: new Date(Date.parse(now) + ttlMs).toISOString(),
    status: 'DRAFTED',
    ...stateFields(),
  };
  return workflowResult(draft, eventFor('DRAFT_CREATED', draft, now), {
    ok: true,
    user_action_required: 'REVIEW',
  });
}

export function approveDraft({
  draft,
  currentSnapshot,
  actorRole,
  now,
  approvalActionId,
}) {
  const guard = guardAction({ draft, currentSnapshot, now });
  if (guard) return guard;
  const parsedDraft = parseDraft(draft);
  if (actorRole !== ALLOWED_ACTOR_ROLE) {
    return workflowResult(
      parsedDraft,
      eventFor('INPUT_REJECTED', parsedDraft, now, 'ROLE_NOT_ALLOWED'),
      {
        error_code: 'ROLE_NOT_ALLOWED',
        error_message: '只有 SUPPORT_AGENT 可以审核本地草稿。',
      },
    );
  }
  if (!isNonEmptyString(approvalActionId, 256)) {
    return invalidInput(now, '审核动作标识无效。', parsedDraft);
  }
  if (parsedDraft.status === 'APPROVED') {
    if (parsedDraft.approval_action_id === approvalActionId) {
      return workflowResult(
        parsedDraft,
        eventFor('APPROVAL_REPLAYED', parsedDraft, now),
        { ok: true },
      );
    }
    return workflowResult(
      parsedDraft,
      eventFor('INPUT_REJECTED', parsedDraft, now, 'ALREADY_APPROVED'),
      {
        error_code: 'ALREADY_APPROVED',
        error_message: '该草稿已经审核通过，不能用新的动作覆盖。',
      },
    );
  }
  if (parsedDraft.status !== 'DRAFTED') {
    return workflowResult(
      parsedDraft,
      eventFor('INPUT_REJECTED', parsedDraft, now, 'INVALID_STATE'),
      {
        error_code: 'INVALID_STATE',
        error_message: '当前草稿状态不能继续审核。',
      },
    );
  }
  const next = {
    ...parsedDraft,
    status: 'APPROVED',
    approved_at: now,
    approval_action_id: approvalActionId,
    failure_code: null,
  };
  return workflowResult(next, eventFor('DRAFT_APPROVED', next, now), {
    ok: true,
  });
}

export function revokeDraft({
  draft,
  currentSnapshot,
  actorRole,
  now,
  revokeActionId,
}) {
  const guard = guardAction({ draft, currentSnapshot, now });
  if (guard) return guard;
  const parsedDraft = parseDraft(draft);
  if (actorRole !== ALLOWED_ACTOR_ROLE) {
    return workflowResult(
      parsedDraft,
      eventFor('INPUT_REJECTED', parsedDraft, now, 'ROLE_NOT_ALLOWED'),
      {
        error_code: 'ROLE_NOT_ALLOWED',
        error_message: '只有 SUPPORT_AGENT 可以撤回本地草稿。',
      },
    );
  }
  if (!isNonEmptyString(revokeActionId, 256)) {
    return invalidInput(now, '撤回动作标识无效。', parsedDraft);
  }
  if (parsedDraft.status === 'REVOKED') {
    if (parsedDraft.revoke_action_id === revokeActionId) {
      return workflowResult(parsedDraft, eventFor('DRAFT_REVOKED', parsedDraft, now), {
        ok: true,
      });
    }
    return workflowResult(
      parsedDraft,
      eventFor('INPUT_REJECTED', parsedDraft, now, 'ALREADY_REVOKED'),
      {
        error_code: 'ALREADY_REVOKED',
        error_message: '该草稿已经撤回，不能重复覆盖。',
      },
    );
  }
  if (!['DRAFTED', 'APPROVED'].includes(parsedDraft.status)) {
    return workflowResult(
      parsedDraft,
      eventFor('INPUT_REJECTED', parsedDraft, now, 'INVALID_STATE'),
      {
        error_code: 'INVALID_STATE',
        error_message: '当前草稿状态不能撤回。',
      },
    );
  }
  const next = {
    ...parsedDraft,
    status: 'REVOKED',
    approved_at: null,
    approval_action_id: null,
    revoke_action_id: revokeActionId,
    send_action_id: null,
    send_requested_at: null,
    failure_code: 'DRAFT_REVOKED',
  };
  return workflowResult(next, eventFor('DRAFT_REVOKED', next, now, 'DRAFT_REVOKED'), {
    ok: true,
  });
}

export function recordSendIntent({
  draft,
  currentSnapshot,
  actorRole,
  now,
  sendActionId,
  confirmation,
}) {
  const guard = guardAction({ draft, currentSnapshot, now });
  if (guard) return guard;
  const parsedDraft = parseDraft(draft);
  if (actorRole !== ALLOWED_ACTOR_ROLE) {
    return workflowResult(
      parsedDraft,
      eventFor('INPUT_REJECTED', parsedDraft, now, 'ROLE_NOT_ALLOWED'),
      {
        error_code: 'ROLE_NOT_ALLOWED',
        error_message: '只有 SUPPORT_AGENT 可以记录发送意图。',
      },
    );
  }
  if (!isNonEmptyString(sendActionId, 256)) {
    return invalidInput(now, '发送动作标识无效。', parsedDraft);
  }
  if (parsedDraft.status === 'SEND_BLOCKED_NOT_CONFIGURED') {
    if (parsedDraft.send_action_id === sendActionId) {
      return workflowResult(
        parsedDraft,
        eventFor('SEND_REPLAYED', parsedDraft, now, 'NOT_CONFIGURED'),
        {
          error_code: 'NOT_CONFIGURED',
          error_message: '已记录同一个本地发送意图；没有发送到闲鱼。',
          user_action_required: 'MANUAL_SEND_ON_OFFICIAL_PAGE',
        },
      );
    }
    return workflowResult(
      parsedDraft,
      eventFor('INPUT_REJECTED', parsedDraft, now, 'SEND_ALREADY_REQUESTED'),
      {
        error_code: 'SEND_ALREADY_REQUESTED',
        error_message: '该草稿已经记录过发送意图，不能重复提交。',
        user_action_required: 'MANUAL_SEND_ON_OFFICIAL_PAGE',
      },
    );
  }
  if (['REVOKED', 'EXPIRED', 'FAILED_CLOSED'].includes(parsedDraft.status)) {
    return workflowResult(
      parsedDraft,
      eventFor('INPUT_REJECTED', parsedDraft, now, 'INVALID_STATE'),
      {
        error_code: 'INVALID_STATE',
        error_message: '当前草稿状态不能记录发送意图。',
      },
    );
  }
  if (parsedDraft.status !== 'APPROVED') {
    return workflowResult(
      parsedDraft,
      eventFor('INPUT_REJECTED', parsedDraft, now, 'REVIEW_REQUIRED'),
      {
        error_code: 'REVIEW_REQUIRED',
        error_message: '发送意图前必须先完成人工审核。',
      },
    );
  }
  if (confirmation !== 'CONFIRM_SEND') {
    return workflowResult(
      parsedDraft,
      eventFor('INPUT_REJECTED', parsedDraft, now, 'CONFIRMATION_REQUIRED'),
      {
        error_code: 'CONFIRMATION_REQUIRED',
        error_message: '记录发送意图需要二次确认。',
      },
    );
  }
  const next = {
    ...parsedDraft,
    status: 'SEND_BLOCKED_NOT_CONFIGURED',
    send_action_id: sendActionId,
    send_requested_at: now,
    failure_code: 'NOT_CONFIGURED',
  };
  return workflowResult(
    next,
    eventFor('SEND_BLOCKED_NOT_CONFIGURED', next, now, 'NOT_CONFIGURED'),
    {
      error_code: 'NOT_CONFIGURED',
      error_message:
        '只记录了本地 send-intent；没有网络请求、没有自动点击，必须由您在官方闲鱼页面手动发送。',
      user_action_required: 'MANUAL_SEND_ON_OFFICIAL_PAGE',
    },
  );
}

export function appendResult(previous, result) {
  if (!result?.draft || !parseDraft(result.draft)) return null;
  if (!result.audit_event) return null;
  const previousSnapshot = previous ? parseWorkflowSnapshot(previous) : null;
  const canReuse = Boolean(
    previousSnapshot &&
      previousSnapshot.visible_session.tab_ref === result.draft.context.tab_ref &&
      previousSnapshot.visible_session.connection_ref === result.draft.context.connection_ref &&
      previousSnapshot.visible_session.account_ref === result.draft.context.account_ref &&
      previousSnapshot.visible_session.conversation_ref === result.draft.context.conversation_ref,
  );
  const auditEvents = [
    ...(canReuse ? previousSnapshot.audit_events : []),
    result.audit_event,
  ].slice(-MAX_AUDIT_EVENTS);
  const snapshot = {
    schema_version: 1,
    visible_session: canReuse ? previousSnapshot.visible_session : null,
    draft: result.draft,
    audit_events: auditEvents,
  };
  if (!snapshot.visible_session) return null;
  return {
    ...snapshot,
    visible_session: parseVisibleSessionSnapshot(snapshot.visible_session),
  };
}

export function makeWorkflowSnapshot(snapshot, draft, auditEvent) {
  const parsedSnapshot = parseVisibleSessionSnapshot(snapshot);
  const parsedDraft = parseDraft(draft);
  if (!parsedSnapshot || !parsedDraft || !auditEvent) return null;
  return {
    schema_version: 1,
    visible_session: parsedSnapshot,
    draft: parsedDraft,
    audit_events: [auditEvent],
  };
}

export function resultSnapshot(previous, currentSnapshot, result) {
  if (!result?.draft || !result.audit_event) return null;
  const parsedCurrent = parseVisibleSessionSnapshot(currentSnapshot);
  if (!parsedCurrent || !parseDraft(result.draft)) return null;
  const parsedPrevious = previous ? parseWorkflowSnapshot(previous) : null;
  const sameContextAsPrevious = Boolean(
    parsedPrevious &&
      contextsEqual(parsedPrevious.visible_session, parsedCurrent) &&
      parsedPrevious.visible_session.tab_ref === result.draft.context.tab_ref,
  );
  return {
    schema_version: 1,
    visible_session: parsedCurrent,
    draft: result.draft,
    audit_events: [
      ...(sameContextAsPrevious ? parsedPrevious.audit_events : []),
      result.audit_event,
    ].slice(-MAX_AUDIT_EVENTS),
  };
}

export function isNoExternalSideEffectResult(result) {
  return Boolean(
    result && result.external_request_started === false && result.sent === false,
  );
}
