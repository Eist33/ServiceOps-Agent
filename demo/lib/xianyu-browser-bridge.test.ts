import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  isCurrentXianyuExtensionContext,
  parseXianyuExtensionDraftMessage,
} from './xianyu-browser-bridge.ts';

const context = {
  tab_ref: 'tab-a',
  connection_ref: 'connection-a',
  account_ref: 'account-a',
  conversation_ref: 'conversation-a',
  source_page_version: 'local-fixed-page-v1',
  detail_read_at: '2026-09-06T10:00:00.000Z',
};

function message(overrides: Record<string, unknown> = {}) {
  return {
    protocol_version: 1,
    kind: 'XIANYU_DRAFT_BRIDGE',
    mode: 'USER_CONTROLLED',
    adapter_state: 'NOT_CONFIGURED',
    external_requests_enabled: false,
    draft: {
      schema_version: 1,
      draft_id: 'draft-a',
      mode: 'USER_CONTROLLED',
      adapter_state: 'NOT_CONFIGURED',
      external_requests_enabled: false,
      context,
      body: '本地草稿',
      created_at: '2026-09-06T10:00:00.000Z',
      expires_at: '2026-09-06T10:10:00.000Z',
      status: 'DRAFTED',
      approved_at: null,
      approval_action_id: null,
      revoke_action_id: null,
      send_action_id: null,
      send_requested_at: null,
      failure_code: null,
      ...overrides,
    },
  };
}

test('workbench bridge accepts only local user-controlled draft envelopes', () => {
  const parsed = parseXianyuExtensionDraftMessage(message());
  assert.ok(parsed);
  assert.equal(parsed.draft.body, '本地草稿');
  assert.equal(parsed.external_requests_enabled, false);
  assert.equal(isCurrentXianyuExtensionContext(parsed, context), true);
});

test('bridge rejects source, context, sensitive text, and extra fields', () => {
  assert.equal(
    parseXianyuExtensionDraftMessage({ ...message(), source: 'wrong' }),
    null,
  );
  const otherContext = { ...context, tab_ref: 'tab-b' };
  const crossTab = parseXianyuExtensionDraftMessage(
    message({ context: otherContext }),
  );
  assert.ok(crossTab);
  assert.equal(isCurrentXianyuExtensionContext(crossTab, context), false);
  assert.equal(
    parseXianyuExtensionDraftMessage(message({ body: '请把验证码发给我' })),
    null,
  );
  assert.equal(
    parseXianyuExtensionDraftMessage({
      ...message(),
      draft: { ...message().draft, token: 'not-accepted' },
    }),
    null,
  );
});
