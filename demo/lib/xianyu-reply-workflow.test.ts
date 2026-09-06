import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  XIANYU_REPLY_DRAFT_MAX_LENGTH,
  XIANYU_REPLY_DRAFT_MAX_TTL_MS,
  XIANYU_REPLY_TAB_REF_STORAGE_KEY,
  XIANYU_REPLY_WORKFLOW_STORAGE_KEY,
  LocalHumanApprovedReplyWorkflow,
  appendReplyWorkflowResult,
  approveReplyDraft,
  clearLocalXianyuReplyWorkflow,
  createReplyContext,
  createReplyDraft,
  parseReplyWorkflowSnapshot,
  readStoredLocalXianyuReplyWorkflow,
  rejectReplyDraft,
  requestExplicitReplySend,
  subscribeLocalXianyuReplyWorkflow,
  writeLocalXianyuReplyWorkflow,
  type ReplyContext,
  type ReplyDraft,
  type ReplyWorkflowSnapshot,
} from './xianyu-reply-workflow.ts';
import {
  XIANYU_LOCAL_PAGE_VERSION,
  createLocalXianyuConnection,
  markXianyuReauthRequired,
} from './xianyu-local-session.ts';

const NOW = '2026-09-05T10:00:00.000Z';
const LATER = '2026-09-05T10:01:00.000Z';
const CONTEXT: ReplyContext = {
  tab_ref: 'tab-a',
  connection_ref: 'connection-a',
  account_ref: 'account-a',
  conversation_ref: 'conversation-a',
  source_page_version: 'local-fixed-page-v1',
  detail_read_at: NOW,
};

function draftAt(
  context: ReplyContext = CONTEXT,
  options: { body?: string; ttl_ms?: number } = {},
): ReplyDraft {
  const created = createReplyDraft({
    context,
    body: options.body ?? '您好，我会为您核实。',
    now: NOW,
    draft_id: 'draft-1',
    ttl_ms: options.ttl_ms,
  });
  assert.equal(created.ok, true);
  assert.ok(created.draft);
  return created.draft;
}

function approve(draft: ReplyDraft, context: ReplyContext = CONTEXT) {
  return approveReplyDraft({
    draft,
    actor_role: 'SUPPORT_AGENT',
    current_context: context,
    now: LATER,
    approval_action_id: 'approval-1',
  });
}

void test('createReplyDraft emits a local reviewable draft with no send capability', () => {
  const result = createReplyDraft({
    context: CONTEXT,
    body: '  您好，我会为您核实。  ',
    now: NOW,
    draft_id: 'draft-1',
    ttl_ms: 60_000,
  });

  assert.equal(result.ok, true);
  assert.equal(result.status, 'DRAFTED');
  assert.equal(result.draft?.body, '您好，我会为您核实。');
  assert.equal(result.draft?.expires_at, '2026-09-05T10:01:00.000Z');
  assert.equal(result.external_request_started, false);
  assert.equal(result.sent, false);
  assert.equal(result.user_action_required, 'REVIEW');
  assert.equal(result.audit_event.event_type, 'DRAFT_CREATED');
  assert.equal(result.audit_event.body_length, '您好，我会为您核实。'.length);
  assert.equal(JSON.stringify(result.audit_event).includes('核实'), false);
});

void test('draft input boundaries are explicit and do not create a partial draft', () => {
  const tooLong = 'a'.repeat(XIANYU_REPLY_DRAFT_MAX_LENGTH + 1);
  for (const input of [
    { body: '', ttl_ms: 60_000 },
    { body: tooLong, ttl_ms: 60_000 },
    { body: '有效内容', ttl_ms: 0 },
    { body: '有效内容', ttl_ms: XIANYU_REPLY_DRAFT_MAX_TTL_MS + 1 },
  ]) {
    const result = createReplyDraft({
      context: CONTEXT,
      body: input.body,
      now: NOW,
      draft_id: 'invalid-draft',
      ttl_ms: input.ttl_ms,
    });
    assert.equal(result.ok, false);
    assert.equal(result.draft, null);
    assert.equal(result.external_request_started, false);
    assert.equal(result.sent, false);
  }

  const max = createReplyDraft({
    context: CONTEXT,
    body: 'a'.repeat(XIANYU_REPLY_DRAFT_MAX_LENGTH),
    now: NOW,
    draft_id: 'max-draft',
    ttl_ms: XIANYU_REPLY_DRAFT_MAX_TTL_MS,
  });
  assert.equal(max.ok, true);
});

void test('only a support agent can approve, and approval binds the full context', () => {
  const draft = draftAt();
  const unauthorized = approveReplyDraft({
    draft,
    actor_role: 'CUSTOMER',
    current_context: CONTEXT,
    now: LATER,
    approval_action_id: 'approval-customer',
  });
  assert.equal(unauthorized.ok, false);
  assert.equal(unauthorized.error_code, 'ROLE_NOT_ALLOWED');
  assert.equal(unauthorized.status, 'DRAFTED');

  for (const changedContext of [
    { ...CONTEXT, connection_ref: 'connection-b' },
    { ...CONTEXT, account_ref: 'account-b' },
    { ...CONTEXT, conversation_ref: 'conversation-b' },
    { ...CONTEXT, tab_ref: 'tab-b' },
    { ...CONTEXT, source_page_version: 'local-fixed-page-v2' },
    { ...CONTEXT, detail_read_at: '2026-09-05T10:00:01.000Z' },
  ]) {
    const result = approve(draft, changedContext);
    assert.equal(result.ok, false);
    assert.equal(result.status, 'FAILED_CLOSED');
    assert.ok(
      result.error_code === 'CONTEXT_MISMATCH' ||
        result.error_code === 'PAGE_CHANGED',
    );
    assert.equal(result.external_request_started, false);
  }
});

void test('approval is idempotent for the same action and rejects a new replay key', () => {
  const draft = draftAt();
  const first = approve(draft);
  assert.equal(first.ok, true);
  assert.ok(first.draft);

  const replay = approveReplyDraft({
    draft: first.draft,
    actor_role: 'SUPPORT_AGENT',
    current_context: CONTEXT,
    now: '2026-09-05T10:01:01.000Z',
    approval_action_id: 'approval-1',
  });
  assert.equal(replay.ok, true);
  assert.equal(replay.status, 'APPROVED');
  assert.equal(replay.audit_event.event_type, 'APPROVAL_REPLAYED');

  const secondKey = approveReplyDraft({
    draft: first.draft,
    actor_role: 'SUPPORT_AGENT',
    current_context: CONTEXT,
    now: '2026-09-05T10:01:02.000Z',
    approval_action_id: 'approval-2',
  });
  assert.equal(secondKey.ok, false);
  assert.equal(secondKey.error_code, 'ALREADY_APPROVED');
});

void test('expiry is fail-closed at the exact boundary and uses no stale approval', () => {
  const draft = draftAt(CONTEXT, { ttl_ms: 60_000 });
  const expired = approveReplyDraft({
    draft,
    actor_role: 'SUPPORT_AGENT',
    current_context: CONTEXT,
    now: '2026-09-05T10:01:00.000Z',
    approval_action_id: 'approval-expired',
  });
  assert.equal(expired.ok, false);
  assert.equal(expired.status, 'EXPIRED');
  assert.equal(expired.error_code, 'DRAFT_EXPIRED');
  assert.equal(expired.draft?.approval_action_id, null);
  assert.equal(expired.audit_event.event_type, 'DRAFT_EXPIRED');
});

void test('rejecting a draft is an explicit, idempotency-scoped review decision', () => {
  const draft = draftAt();
  const rejected = rejectReplyDraft({
    draft,
    actor_role: 'SUPPORT_AGENT',
    current_context: CONTEXT,
    now: LATER,
    rejection_action_id: 'reject-1',
  });
  assert.equal(rejected.ok, true);
  assert.equal(rejected.status, 'REJECTED');
  assert.equal(rejected.error_code, null);
  assert.equal(rejected.draft?.failure_code, 'DRAFT_REJECTED');

  const cannotApprove = approveReplyDraft({
    draft: rejected.draft as ReplyDraft,
    actor_role: 'SUPPORT_AGENT',
    current_context: CONTEXT,
    now: '2026-09-05T10:01:01.000Z',
    approval_action_id: 'approval-after-reject',
  });
  assert.equal(cannotApprove.ok, false);
  assert.equal(cannotApprove.error_code, 'INVALID_STATE');
});

void test('an approved draft can be revoked before a send intent and cannot be reused', () => {
  const approved = approve(draftAt());
  assert.ok(approved.draft);

  const revoked = rejectReplyDraft({
    draft: approved.draft,
    actor_role: 'SUPPORT_AGENT',
    current_context: CONTEXT,
    now: '2026-09-05T10:01:30.000Z',
    rejection_action_id: 'revoke-1',
  });
  assert.equal(revoked.ok, true);
  assert.equal(revoked.status, 'REJECTED');
  assert.equal(revoked.draft?.approved_at, null);
  assert.equal(revoked.draft?.approval_action_id, null);
  assert.equal(revoked.draft?.send_action_id, null);

  const cannotSend = requestExplicitReplySend({
    draft: revoked.draft as ReplyDraft,
    actor_role: 'SUPPORT_AGENT',
    current_context: CONTEXT,
    now: '2026-09-05T10:02:00.000Z',
    send_action_id: 'send-after-revoke',
    confirmation: 'CONFIRM_SEND',
  });
  assert.equal(cannotSend.ok, false);
  assert.equal(cannotSend.error_code, 'REVIEW_REQUIRED');
  assert.equal(cannotSend.external_request_started, false);
});

void test('explicit send requires approval and a second confirmation', () => {
  const draft = draftAt();
  const beforeApproval = requestExplicitReplySend({
    draft,
    actor_role: 'SUPPORT_AGENT',
    current_context: CONTEXT,
    now: LATER,
    send_action_id: 'send-1',
    confirmation: 'CONFIRM_SEND',
  });
  assert.equal(beforeApproval.ok, false);
  assert.equal(beforeApproval.error_code, 'REVIEW_REQUIRED');
  assert.equal(beforeApproval.status, 'DRAFTED');

  const approved = approve(draft);
  assert.ok(approved.draft);
  const missingConfirmation = requestExplicitReplySend({
    draft: approved.draft,
    actor_role: 'SUPPORT_AGENT',
    current_context: CONTEXT,
    now: '2026-09-05T10:02:00.000Z',
    send_action_id: 'send-1',
    confirmation: null,
  });
  assert.equal(missingConfirmation.ok, false);
  assert.equal(missingConfirmation.error_code, 'CONFIRMATION_REQUIRED');
  assert.equal(missingConfirmation.status, 'APPROVED');
  assert.equal(missingConfirmation.external_request_started, false);
});

void test('explicit send is fail-closed as NOT_CONFIGURED and never claims delivery', () => {
  const approved = approve(draftAt());
  assert.ok(approved.draft);
  const blocked = requestExplicitReplySend({
    draft: approved.draft,
    actor_role: 'SUPPORT_AGENT',
    current_context: CONTEXT,
    now: '2026-09-05T10:02:00.000Z',
    send_action_id: 'send-1',
    confirmation: 'CONFIRM_SEND',
  });
  assert.equal(blocked.ok, false);
  assert.equal(blocked.status, 'SEND_BLOCKED_NOT_CONFIGURED');
  assert.equal(blocked.error_code, 'NOT_CONFIGURED');
  assert.equal(blocked.user_action_required, 'MANUAL_SEND_ON_OFFICIAL_PAGE');
  assert.equal(blocked.external_request_started, false);
  assert.equal(blocked.sent, false);
  assert.equal(blocked.draft?.send_action_id, 'send-1');
  assert.equal(blocked.audit_event.body_length > 0, true);
  assert.equal(JSON.stringify(blocked.audit_event).includes('核实'), false);
});

void test('send request is idempotent and a different key cannot retry it', () => {
  const approved = approve(draftAt());
  assert.ok(approved.draft);
  const first = requestExplicitReplySend({
    draft: approved.draft,
    actor_role: 'SUPPORT_AGENT',
    current_context: CONTEXT,
    now: '2026-09-05T10:02:00.000Z',
    send_action_id: 'send-1',
    confirmation: 'CONFIRM_SEND',
  });
  assert.ok(first.draft);

  const replay = requestExplicitReplySend({
    draft: first.draft,
    actor_role: 'SUPPORT_AGENT',
    current_context: CONTEXT,
    now: '2026-09-05T10:02:01.000Z',
    send_action_id: 'send-1',
    confirmation: 'CONFIRM_SEND',
  });
  assert.equal(replay.error_code, 'NOT_CONFIGURED');
  assert.equal(replay.audit_event.event_type, 'SEND_REPLAYED');

  const differentKey = requestExplicitReplySend({
    draft: first.draft,
    actor_role: 'SUPPORT_AGENT',
    current_context: CONTEXT,
    now: '2026-09-05T10:02:02.000Z',
    send_action_id: 'send-2',
    confirmation: 'CONFIRM_SEND',
  });
  assert.equal(differentKey.error_code, 'SEND_ALREADY_REQUESTED');
  assert.equal(differentKey.external_request_started, false);
});

void test('page/account/session change after approval fails closed before send', () => {
  const approved = approve(draftAt());
  assert.ok(approved.draft);
  const changed = requestExplicitReplySend({
    draft: approved.draft,
    actor_role: 'SUPPORT_AGENT',
    current_context: { ...CONTEXT, account_ref: 'account-b' },
    now: '2026-09-05T10:02:00.000Z',
    send_action_id: 'send-cross-account',
    confirmation: 'CONFIRM_SEND',
  });
  assert.equal(changed.ok, false);
  assert.equal(changed.status, 'FAILED_CLOSED');
  assert.equal(changed.error_code, 'CONTEXT_MISMATCH');
  assert.equal(changed.draft?.send_action_id, null);
  assert.equal(changed.external_request_started, false);
});

void test('forged or structurally inconsistent drafts fail closed without throwing', () => {
  const draft = draftAt();
  const forged = {
    ...draft,
    approved_at: LATER,
    approval_action_id: 'forged-approval',
  } as ReplyDraft;

  assert.equal(
    parseReplyWorkflowSnapshot(
      JSON.stringify({
        schema_version: 1,
        draft: forged,
        audit_events: [],
      }),
    ),
    null,
  );

  const result = approveReplyDraft({
    draft: { ...draft, body: undefined } as unknown as ReplyDraft,
    actor_role: 'SUPPORT_AGENT',
    current_context: CONTEXT,
    now: LATER,
    approval_action_id: 'forged-input',
  });
  assert.equal(result.ok, false);
  assert.equal(result.error_code, 'INVALID_INPUT');
  assert.equal(result.draft, null);
  assert.equal(result.external_request_started, false);
  assert.equal(result.sent, false);
});

void test('context creation requires one connected fixed page and binds the active tab', () => {
  const previousWindow = Object.getOwnPropertyDescriptor(globalThis, 'window');
  const connection = createLocalXianyuConnection('account-a', { now: NOW });

  try {
    Object.defineProperty(globalThis, 'window', {
      configurable: true,
      value: undefined,
    });
    assert.throws(
      () =>
        createReplyContext(
          connection,
          'conversation-a',
          XIANYU_LOCAL_PAGE_VERSION,
          NOW,
        ),
      /浏览器标签页/,
    );

    const firstTabStorage = installMemorySessionStorage();
    const first = createReplyContext(
      connection,
      'conversation-a',
      XIANYU_LOCAL_PAGE_VERSION,
      NOW,
    );
    const sameTab = createReplyContext(
      connection,
      'conversation-a',
      XIANYU_LOCAL_PAGE_VERSION,
      NOW,
    );
    assert.equal(first.tab_ref, sameTab.tab_ref);
    assert.equal(
      firstTabStorage.getItem(XIANYU_REPLY_TAB_REF_STORAGE_KEY),
      first.tab_ref,
    );

    const secondTabStorage = installMemorySessionStorage();
    const second = createReplyContext(
      connection,
      'conversation-a',
      XIANYU_LOCAL_PAGE_VERSION,
      NOW,
    );
    assert.notEqual(first.tab_ref, second.tab_ref);
    assert.notEqual(
      firstTabStorage.getItem(XIANYU_REPLY_TAB_REF_STORAGE_KEY),
      secondTabStorage.getItem(XIANYU_REPLY_TAB_REF_STORAGE_KEY),
    );

    assert.throws(
      () =>
        createReplyContext(
          markXianyuReauthRequired(connection),
          'conversation-a',
          XIANYU_LOCAL_PAGE_VERSION,
          NOW,
        ),
      /无法确认/,
    );
  } finally {
    if (previousWindow) {
      Object.defineProperty(globalThis, 'window', previousWindow);
    } else {
      Reflect.deleteProperty(globalThis, 'window');
    }
  }
});

void test('local workflow class exposes the same side-effect-free contract', () => {
  const workflow = new LocalHumanApprovedReplyWorkflow();
  const created = workflow.createDraft({
    context: CONTEXT,
    body: '本地草稿',
    now: NOW,
    draft_id: 'class-draft',
  });
  assert.equal(created.ok, true);
  assert.ok(created.draft);
  const approved = workflow.approveDraft({
    draft: created.draft,
    actor_role: 'SUPPORT_AGENT',
    current_context: CONTEXT,
    now: LATER,
    approval_action_id: 'class-approval',
  });
  assert.equal(approved.ok, true);
});

void test('snapshot parsing is strict, stores only bounded local audit, and clears idempotently', () => {
  const created = createReplyDraft({
    context: CONTEXT,
    body: '本地草稿',
    now: NOW,
    draft_id: 'stored-draft',
  });
  assert.ok(created.draft);
  const snapshot = appendReplyWorkflowResult(null, created);
  assert.ok(snapshot);
  assert.deepEqual(
    parseReplyWorkflowSnapshot(JSON.stringify(snapshot)),
    snapshot,
  );
  assert.equal(
    parseReplyWorkflowSnapshot(
      JSON.stringify({
        ...snapshot,
        draft: { ...snapshot.draft, token: 'secret' },
      }),
    ),
    null,
  );
  assert.equal(
    parseReplyWorkflowSnapshot(
      JSON.stringify({ ...snapshot, audit_events: ['bad'] }),
    ),
    null,
  );
  assert.equal(
    parseReplyWorkflowSnapshot(
      JSON.stringify({ ...snapshot, audit_events: [] }),
    ),
    null,
  );
  assert.equal(
    parseReplyWorkflowSnapshot(
      JSON.stringify({
        ...snapshot,
        audit_events: [
          { ...snapshot.audit_events[0], draft_id: 'another-draft' },
        ],
      }),
    ),
    null,
  );

  installMemorySessionStorage();
  let notifications = 0;
  const unsubscribe = subscribeLocalXianyuReplyWorkflow(() => {
    notifications += 1;
  });
  writeLocalXianyuReplyWorkflow(snapshot);
  assert.deepEqual(readStoredLocalXianyuReplyWorkflow(), snapshot);
  assert.equal(
    window.sessionStorage.getItem(XIANYU_REPLY_WORKFLOW_STORAGE_KEY),
    JSON.stringify(snapshot),
  );
  clearLocalXianyuReplyWorkflow();
  clearLocalXianyuReplyWorkflow();
  assert.equal(readStoredLocalXianyuReplyWorkflow(), null);
  assert.equal(notifications, 3);
  unsubscribe();
});

void test('stored workflow state is isolated to one browser tab', () => {
  const created = createReplyDraft({
    context: CONTEXT,
    body: '只在当前标签页保留',
    now: NOW,
    draft_id: 'tab-a-draft',
  });
  assert.ok(created.draft);
  const snapshot = appendReplyWorkflowResult(null, created);
  assert.ok(snapshot);

  installMemorySessionStorage();
  writeLocalXianyuReplyWorkflow(snapshot);
  assert.ok(readStoredLocalXianyuReplyWorkflow());

  installMemorySessionStorage();
  assert.equal(readStoredLocalXianyuReplyWorkflow(), null);
});

void test('snapshot append keeps the latest audit events and preserves prior history', () => {
  const created = createReplyDraft({
    context: CONTEXT,
    body: '草稿',
    now: NOW,
    draft_id: 'history-draft',
  });
  assert.ok(created.draft);
  const previous: ReplyWorkflowSnapshot = {
    schema_version: 1,
    draft: created.draft,
    audit_events: Array.from({ length: 50 }, (_, index) => ({
      ...created.audit_event,
      event_id: `event-${index}`,
    })),
  };
  const approved = approve(created.draft);
  const next = appendReplyWorkflowResult(previous, approved);
  assert.ok(next);
  assert.equal(next.audit_events.length, 50);
  assert.equal(next.audit_events[0].event_id, 'event-1');
  assert.equal(next.audit_events.at(-1)?.event_type, 'DRAFT_APPROVED');
});

void test('snapshot append starts a fresh audit chain for another draft or tab', () => {
  const created = createReplyDraft({
    context: CONTEXT,
    body: '旧草稿',
    now: NOW,
    draft_id: 'old-draft',
  });
  const replacement = createReplyDraft({
    context: { ...CONTEXT, tab_ref: 'tab-b' },
    body: '新草稿',
    now: NOW,
    draft_id: 'new-draft',
  });
  assert.ok(created.draft);
  assert.ok(replacement.draft);
  const previous = appendReplyWorkflowResult(null, created);
  assert.ok(previous);

  const next = appendReplyWorkflowResult(previous, replacement);
  assert.ok(next);
  assert.equal(next.draft.draft_id, 'new-draft');
  assert.equal(next.draft.context.tab_ref, 'tab-b');
  assert.equal(next.audit_events.length, 1);
  assert.equal(next.audit_events[0].draft_id, 'new-draft');
});

function installMemorySessionStorage() {
  const values = new Map<string, string>();
  const sessionStorage = {
    getItem(key: string) {
      return values.get(key) ?? null;
    },
    setItem(key: string, value: string) {
      values.set(key, value);
    },
    removeItem(key: string) {
      values.delete(key);
    },
  } as unknown as Storage;
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: { sessionStorage },
  });
  return sessionStorage;
}
