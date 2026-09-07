import assert from 'node:assert/strict';
import test from 'node:test';

import {
  refundApprovalActions,
  refundApprovalStatusLabel,
} from './refund-approval.ts';

void test('客服审批区只为允许的状态提供动作', () => {
  assert.deepEqual(refundApprovalActions('PENDING_HUMAN_APPROVAL'), [
    'APPROVE',
    'REJECT',
  ]);
  assert.deepEqual(refundApprovalActions('PENDING_CONFIRMATION'), [
    'WITHDRAW',
  ]);
  for (const status of ['REJECTED', 'WITHDRAWN', 'SUCCEEDED', 'CANCELLED']) {
    assert.deepEqual(refundApprovalActions(status), []);
  }
});

void test('审批状态显示为面向坐席的中文标签', () => {
  assert.equal(
    refundApprovalStatusLabel('PENDING_HUMAN_APPROVAL'),
    '待客服审批',
  );
  assert.equal(
    refundApprovalStatusLabel('PENDING_CONFIRMATION'),
    '待客户确认（可撤回）',
  );
  assert.equal(refundApprovalStatusLabel('UNKNOWN'), 'UNKNOWN');
});
