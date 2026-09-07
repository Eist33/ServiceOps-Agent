export type RefundApprovalAction = 'APPROVE' | 'REJECT' | 'WITHDRAW';

export function refundApprovalActions(
  status: string,
): readonly RefundApprovalAction[] {
  if (status === 'PENDING_HUMAN_APPROVAL') return ['APPROVE', 'REJECT'];
  if (status === 'PENDING_CONFIRMATION') return ['WITHDRAW'];
  return [];
}

export function refundApprovalStatusLabel(status: string): string {
  return (
    {
      PENDING_HUMAN_APPROVAL: '待客服审批',
      PENDING_CONFIRMATION: '待客户确认（可撤回）',
      REJECTED: '已拒绝',
      WITHDRAWN: '已撤回',
      SUCCEEDED: '已退款',
      CANCELLED: '已取消',
    }[status] ?? status
  );
}
