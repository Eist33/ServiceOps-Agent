import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import {
  ADAPTER_STATE,
  BRIDGE_MODE,
  MESSAGE_TYPES,
  LOCAL_VISIBLE_PAGE_VERSION,
  createRequest,
  makeVisibleSessionSnapshot,
  parseRequest,
  parseVisibleSessionSnapshot,
  parseWorkflowSnapshot,
  selectionIsFresh,
} from '../src/protocol.js';
import { readVisibleSessionFromDocument } from '../src/dom-reader.js';
import {
  approveDraft,
  createDraft,
  recordSendIntent,
  resultSnapshot,
  revokeDraft,
} from '../src/workflow.js';
import {
  NOW,
  TAB_REF,
  makeDocument,
} from './fixtures/visible-session.js';

const LATER = '2026-09-06T10:01:00.000Z';

function fixtureSnapshot(overrides = {}) {
  const result = readVisibleSessionFromDocument(makeDocument(overrides), {
    tabRef: TAB_REF,
    now: NOW,
  });
  assert.equal(result.result, 'SUCCESS');
  return result.snapshot;
}

test('Manifest message protocol is strict and extension actions are explicit', () => {
  const request = createRequest(MESSAGE_TYPES.READ_CURRENT_VISIBLE_SESSION);
  assert.equal(parseRequest(request)?.type, MESSAGE_TYPES.READ_CURRENT_VISIBLE_SESSION);
  assert.equal(parseRequest({ ...request, type: 'UNKNOWN' }), null);
  assert.equal(parseRequest({ ...request, payload: 'not-an-object' }), null);
});

test('Chrome and Edge manifests share the minimum user-triggered permission boundary', async () => {
  const [manifest, chromeManifest, edgeManifest] = await Promise.all(
    ['../manifest.json', '../manifests/manifest.chrome.json', '../manifests/manifest.edge.json'].map(
      (path) => readFile(new URL(path, import.meta.url), 'utf8').then(JSON.parse),
    ),
  );
  for (const candidate of [manifest, chromeManifest, edgeManifest]) {
    assert.equal(candidate.manifest_version, 3);
    assert.deepEqual(candidate.permissions, ['activeTab', 'scripting', 'storage']);
    assert.deepEqual(candidate.host_permissions, []);
    assert.equal(candidate.background.service_worker, 'src/service-worker.js');
    assert.equal(candidate.background.type, 'module');
    assert.equal(candidate.action.default_popup, 'src/popup.html');
    assert.equal(Object.hasOwn(candidate, 'content_scripts'), false);
  }
  assert.equal(chromeManifest.permissions.join(','), edgeManifest.permissions.join(','));
});

test('visible DOM reader only accepts one visible, explicitly selected fixture', () => {
  const success = readVisibleSessionFromDocument(makeDocument(), {
    tabRef: TAB_REF,
    now: NOW,
  });
  assert.equal(success.result, 'SUCCESS');
  assert.equal(success.snapshot.mode, BRIDGE_MODE);
  assert.equal(success.snapshot.adapter_state, ADAPTER_STATE);
  assert.equal(success.snapshot.external_requests_enabled, false);
  assert.equal(success.snapshot.messages.length, 1);

  const notSelected = readVisibleSessionFromDocument(
    makeDocument({ selected: false }),
    { tabRef: TAB_REF, now: NOW },
  );
  assert.equal(notSelected.result, 'FAILED');
  assert.equal(notSelected.error_code, 'SESSION_NOT_SELECTED');

  const pageChanged = readVisibleSessionFromDocument(
    makeDocument({ sourcePageVersion: 'unknown-page-v2' }),
    { tabRef: TAB_REF, now: NOW },
  );
  assert.equal(pageChanged.result, 'FAILED');
  assert.equal(pageChanged.error_code, 'IDENTITY_UNCONFIRMED');
});

test('reader rejects sensitive page text without returning it', () => {
  const result = readVisibleSessionFromDocument(
    makeDocument({
      messages: [
        {
          getAttribute(name) {
            return {
              'data-message-id': 'message-sensitive',
              'data-sender': 'OTHER',
              'data-sent-at': NOW,
            }[name] ?? null;
          },
          textContent: '验证码 123456',
        },
      ],
    }),
    { tabRef: TAB_REF, now: NOW },
  );
  assert.equal(result.result, 'FAILED');
  assert.equal(result.error_code, 'IDENTITY_UNCONFIRMED');
  assert.equal(JSON.stringify(result).includes('123456'), false);
});

test('snapshot parser rejects extra fields, cross-tab spoofing, and stale selections', () => {
  const snapshot = fixtureSnapshot();
  assert.ok(parseVisibleSessionSnapshot(snapshot));
  assert.equal(
    parseVisibleSessionSnapshot({ ...snapshot, cookie: 'never-accepted' }),
    null,
  );
  assert.equal(selectionIsFresh(snapshot, '2026-09-06T10:05:01.000Z'), false);
  assert.equal(
    parseVisibleSessionSnapshot({ ...snapshot, tab_ref: 'tab-other' })?.tab_ref,
    'tab-other',
  );
});

test('draft -> human review -> second confirmation -> blocked send-intent', () => {
  const snapshot = fixtureSnapshot();
  const created = createDraft({
    snapshot,
    body: '您好，我会先核实发货时间。',
    now: NOW,
    draftId: 'draft-a',
  });
  assert.equal(created.ok, true);
  assert.equal(created.draft.status, 'DRAFTED');
  assert.equal(created.external_request_started, false);
  assert.equal(created.sent, false);

  const approved = approveDraft({
    draft: created.draft,
    currentSnapshot: snapshot,
    actorRole: 'SUPPORT_AGENT',
    now: LATER,
    approvalActionId: 'approval-a',
  });
  assert.equal(approved.ok, true);
  assert.equal(approved.draft.status, 'APPROVED');

  const blocked = recordSendIntent({
    draft: approved.draft,
    currentSnapshot: snapshot,
    actorRole: 'SUPPORT_AGENT',
    now: '2026-09-06T10:02:00.000Z',
    sendActionId: 'send-a',
    confirmation: 'CONFIRM_SEND',
  });
  assert.equal(blocked.ok, false);
  assert.equal(blocked.draft.status, 'SEND_BLOCKED_NOT_CONFIGURED');
  assert.equal(blocked.error_code, 'NOT_CONFIGURED');
  assert.equal(blocked.external_request_started, false);
  assert.equal(blocked.sent, false);
  assert.equal(blocked.user_action_required, 'MANUAL_SEND_ON_OFFICIAL_PAGE');
});

test('approval and send actions are idempotent; changed action ids are rejected', () => {
  const snapshot = fixtureSnapshot();
  const created = createDraft({ snapshot, body: '本地草稿', now: NOW, draftId: 'draft-idempotent' });
  const approved = approveDraft({
    draft: created.draft,
    currentSnapshot: snapshot,
    actorRole: 'SUPPORT_AGENT',
    now: LATER,
    approvalActionId: 'approval-idempotent',
  });
  const replayApproval = approveDraft({
    draft: approved.draft,
    currentSnapshot: snapshot,
    actorRole: 'SUPPORT_AGENT',
    now: LATER,
    approvalActionId: 'approval-idempotent',
  });
  assert.equal(replayApproval.ok, true);
  assert.equal(replayApproval.audit_event.event_type, 'APPROVAL_REPLAYED');
  const changedApproval = approveDraft({
    draft: approved.draft,
    currentSnapshot: snapshot,
    actorRole: 'SUPPORT_AGENT',
    now: LATER,
    approvalActionId: 'approval-other',
  });
  assert.equal(changedApproval.error_code, 'ALREADY_APPROVED');

  const blocked = recordSendIntent({
    draft: approved.draft,
    currentSnapshot: snapshot,
    actorRole: 'SUPPORT_AGENT',
    now: '2026-09-06T10:02:00.000Z',
    sendActionId: 'send-idempotent',
    confirmation: 'CONFIRM_SEND',
  });
  const replaySend = recordSendIntent({
    draft: blocked.draft,
    currentSnapshot: snapshot,
    actorRole: 'SUPPORT_AGENT',
    now: '2026-09-06T10:02:00.000Z',
    sendActionId: 'send-idempotent',
    confirmation: 'CONFIRM_SEND',
  });
  assert.equal(replaySend.error_code, 'NOT_CONFIGURED');
  assert.equal(replaySend.audit_event.event_type, 'SEND_REPLAYED');
  const changedSend = recordSendIntent({
    draft: blocked.draft,
    currentSnapshot: snapshot,
    actorRole: 'SUPPORT_AGENT',
    now: '2026-09-06T10:02:00.000Z',
    sendActionId: 'send-other',
    confirmation: 'CONFIRM_SEND',
  });
  assert.equal(changedSend.error_code, 'SEND_ALREADY_REQUESTED');
});

test('cross-account, cross-tab and stale page actions fail closed', () => {
  const snapshot = fixtureSnapshot();
  const created = createDraft({ snapshot, body: '本地草稿', now: NOW, draftId: 'draft-context', ttlMs: 2 * 60 * 1_000 });
  const otherAccount = fixtureSnapshot({ accountRef: 'account-b' });
  const accountFailure = approveDraft({
    draft: created.draft,
    currentSnapshot: otherAccount,
    actorRole: 'SUPPORT_AGENT',
    now: LATER,
    approvalActionId: 'approval-context',
  });
  assert.equal(accountFailure.draft.status, 'FAILED_CLOSED');
  assert.equal(accountFailure.error_code, 'CONTEXT_MISMATCH');

  const otherTab = fixtureSnapshot();
  otherTab.tab_ref = 'tab-other';
  const tabFailure = approveDraft({
    draft: created.draft,
    currentSnapshot: otherTab,
    actorRole: 'SUPPORT_AGENT',
    now: LATER,
    approvalActionId: 'approval-other-tab',
  });
  assert.equal(tabFailure.draft.status, 'FAILED_CLOSED');
  assert.equal(tabFailure.error_code, 'CONTEXT_MISMATCH');

  const expired = approveDraft({
    draft: created.draft,
    currentSnapshot: snapshot,
    actorRole: 'SUPPORT_AGENT',
    now: '2026-09-06T10:03:00.000Z',
    approvalActionId: 'approval-expired',
  });
  assert.equal(expired.draft.status, 'EXPIRED');
  assert.equal(expired.error_code, 'DRAFT_EXPIRED');
});

test('revoke is human-only, idempotent, and prevents later send', () => {
  const snapshot = fixtureSnapshot();
  const created = createDraft({ snapshot, body: '撤回草稿', now: NOW, draftId: 'draft-revoke' });
  const denied = revokeDraft({
    draft: created.draft,
    currentSnapshot: snapshot,
    actorRole: 'CUSTOMER',
    now: LATER,
    revokeActionId: 'revoke-denied',
  });
  assert.equal(denied.error_code, 'ROLE_NOT_ALLOWED');
  const revoked = revokeDraft({
    draft: created.draft,
    currentSnapshot: snapshot,
    actorRole: 'SUPPORT_AGENT',
    now: LATER,
    revokeActionId: 'revoke-a',
  });
  assert.equal(revoked.ok, true);
  assert.equal(revoked.draft.status, 'REVOKED');
  const replay = revokeDraft({
    draft: revoked.draft,
    currentSnapshot: snapshot,
    actorRole: 'SUPPORT_AGENT',
    now: LATER,
    revokeActionId: 'revoke-a',
  });
  assert.equal(replay.ok, true);
  const send = recordSendIntent({
    draft: revoked.draft,
    currentSnapshot: snapshot,
    actorRole: 'SUPPORT_AGENT',
    now: LATER,
    sendActionId: 'send-after-revoke',
    confirmation: 'CONFIRM_SEND',
  });
  assert.equal(send.error_code, 'INVALID_STATE');
});

test('workflow snapshot stays local and rejects cross-context audit reuse', () => {
  const snapshot = fixtureSnapshot();
  const created = createDraft({ snapshot, body: '审计草稿', now: NOW, draftId: 'draft-audit' });
  const stored = resultSnapshot(null, snapshot, created);
  assert.ok(stored);
  assert.ok(parseWorkflowSnapshot(stored));
  assert.equal(stored.visible_session.external_requests_enabled, false);
  assert.equal(JSON.stringify(stored.audit_events).includes('审计草稿'), false);
  assert.equal(
    parseWorkflowSnapshot({
      ...stored,
      visible_session: { ...stored.visible_session, account_ref: 'account-b' },
    }),
    null,
  );
});

test('workbench bridge and injected readers contain no outbound transport or credential API', async () => {
  const sources = await Promise.all(
    ['service-worker.js', 'content-script.js', 'workbench-bridge.js', 'popup.js', 'workflow.js'].map(
      (file) => readFile(new URL(`../src/${file}`, import.meta.url), 'utf8'),
    ),
  );
  const source = sources.join('\n');
  assert.equal(/\bfetch\s*\(|\baxios\b|\bWebSocket\b|chrome\.cookies|chrome\.webRequest/.test(source), false);
  assert.equal(/setInterval\s*\(|setTimeout\s*\(/.test(source), false);
  assert.match(source, /external_requests_enabled\s*:\s*false/);
  assert.match(source, /MANUAL_SEND_ON_OFFICIAL_PAGE/);
});

test('fixture snapshot has the expected fixed-page version and no secret fields', () => {
  const snapshot = fixtureSnapshot();
  assert.equal(snapshot.source_page_version, LOCAL_VISIBLE_PAGE_VERSION);
  assert.equal(JSON.stringify(snapshot).toLowerCase().includes('cookie'), false);
  assert.equal(JSON.stringify(snapshot).toLowerCase().includes('token'), false);
  assert.equal(JSON.stringify(snapshot).includes('验证码'), false);
  assert.ok(parseVisibleSessionSnapshot(makeVisibleSessionSnapshot({
    tabRef: TAB_REF,
    connectionRef: 'connection-a',
    accountRef: 'account-a',
    conversationRef: 'conversation-a',
    selectedAt: NOW,
    detailReadAt: NOW,
    messages: [],
  })));
});
