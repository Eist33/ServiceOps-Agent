import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page, request }) => {
  await request.post('http://127.0.0.1:8000/api/demo/reset', {
    headers: { 'X-Demo-Session': 'demo-linmu-session' },
  });
  await page.goto('/');
  await expect(
    page.getByRole('heading', { name: '售后服务助手', exact: true }),
  ).toBeVisible();
  await expect(page.getByText('正在连接业务服务…')).toBeHidden();
});

test('政策问答展示知识来源与工具证据', async ({ page }) => {
  await page
    .getByRole('button', { name: /咨询退货政策/ })
    .first()
    .click();
  await expect(page.getByText(/已调用 search_knowledge_base/)).toBeVisible();
  await expect(page.getByText(/来源：平台退换货规则 2026-07/)).toBeVisible();
});

test('订单物流由工具返回确定性异常', async ({ page }) => {
  await page
    .getByRole('button', { name: /查询订单物流/ })
    .first()
    .click();
  await expect(page.getByText(/已调用 get_order/)).toBeVisible();
  await expect(page.getByText(/已调用 get_shipping_status/)).toBeVisible();
  await expect(page.getByText(/系统规则判定为运输停滞/)).toBeVisible();
});

test('新会话创建独立物流工单', async ({ page }) => {
  await page
    .getByRole('button', { name: /物流异常建单/ })
    .first()
    .click();
  await expect(page.getByText(/已调用 create_ticket/)).toBeVisible();
  await expect(page.getByText(/已创建物流异常工单 TK-/)).toBeVisible();
  await expect(page.getByText(/TK-/).last()).toBeVisible();
  const businessContext = page.getByRole('complementary').last();
  const firstTicketNumber = (await businessContext.textContent())?.match(
    /TK-\d{8}-[A-Z0-9]{6}/,
  )?.[0];
  expect(firstTicketNumber).toBeTruthy();

  await page
    .getByRole('button', { name: /物流异常建单/ })
    .first()
    .click();
  await expect(page.getByText(/已创建物流异常工单 TK-/)).toBeVisible();
  await expect(businessContext.getByText(/TK-/)).toBeVisible();
  await expect(businessContext.getByText('处理中')).toBeVisible();
  await expect
    .poll(async () => {
      const nextNumber = (await businessContext.textContent())?.match(
        /TK-\d{8}-[A-Z0-9]{6}/,
      )?.[0];
      return Boolean(nextNumber && nextNumber !== firstTicketNumber);
    })
    .toBe(true);
  const secondTicketNumber = (await businessContext.textContent())?.match(
    /TK-\d{8}-[A-Z0-9]{6}/,
  )?.[0];
  expect(secondTicketNumber).toBeTruthy();
  expect(secondTicketNumber).not.toBe(firstTicketNumber);
});

test('工单可转人工并展示自动分派与 SLA', async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 800 });
  await page
    .getByRole('button', { name: /物流异常建单/ })
    .first()
    .click();
  await expect(page.getByText(/已创建物流异常工单 TK-/)).toBeVisible();
  await page.getByRole('button', { name: '查看工单详情' }).click();
  await expect(page.getByText('SLA 状态')).toBeVisible();
  await page.getByRole('button', { name: '转人工处理' }).click();
  await expect(page.getByText('人工接管已建立')).toBeVisible();
  await expect(page.getByText('物流专员组').first()).toBeVisible();
  await page.getByRole('button', { name: '撤销人工接管' }).click();
  await expect(page.getByText(/已撤销人工接管/)).toBeVisible();
  await expect(page.getByText('人工接管已建立')).toBeHidden();
  await expect(page.getByText('尚未转人工')).toBeVisible();
  await expect(page.getByRole('button', { name: '转人工处理' })).toBeEnabled();
});

test('人工坐席可受理、记录并解决工单', async ({ page, request }) => {
  const customerHeaders = { 'X-Demo-Session': 'demo-linmu-session' };
  const conversationResponse = await request.post(
    'http://127.0.0.1:8000/api/conversations',
    { headers: customerHeaders },
  );
  const conversation = await conversationResponse.json();
  const ticketResponse = await request.post(
    'http://127.0.0.1:8000/api/tickets',
    {
      headers: customerHeaders,
      data: {
        conversation_id: conversation.id,
        order_number: 'ORD-20260828-1042',
        ticket_type: 'SHIPPING',
        reason: '物流停滞，需要人工联系承运商',
      },
    },
  );
  const ticket = await ticketResponse.json();
  await page.evaluate(
    ({ conversationId }) =>
      localStorage.setItem('harbor-support-conversation', conversationId),
    { conversationId: conversation.id },
  );
  await request.post(
    `http://127.0.0.1:8000/api/tickets/${ticket.id}/handoff`,
    { headers: customerHeaders },
  );

  await page.goto('/agent');
  await expect(page.getByRole('heading', { name: '人工工单队列' })).toBeVisible();
  await expect(page.getByText(ticket.ticket_number).first()).toBeVisible();
  await page.getByRole('button', { name: '受理此工单' }).click();
  await expect(page.getByText(/已受理工单/)).toBeVisible();
  await expect(page.getByText('沈清禾').first()).toBeVisible();

  await page.getByLabel('切换演示坐席').click();
  await page.getByRole('option', { name: '陆川' }).click();
  await expect(page.getByText('已由 沈清禾 受理')).toBeVisible();
  await expect(page.getByLabel('处理记录或解决说明')).toBeHidden();

  await page.getByLabel('切换演示坐席').click();
  await page.getByRole('option', { name: '沈清禾' }).click();
  await expect(page.getByText('由我处理')).toBeVisible();

  const note = page.getByLabel('处理记录或解决说明');
  await note.fill('已联系承运商，确认今晚恢复转运。');
  await page.getByRole('button', { name: '添加处理记录' }).click();
  await expect(page.getByText('已联系承运商，确认今晚恢复转运。')).toBeVisible();

  await note.fill('承运商已恢复转运，客户接受继续等待。');
  await page.getByRole('button', { name: '标记已解决' }).click();
  await expect(page.getByText(/已解决/).first()).toBeVisible();
  await expect(page.getByText('工单已完成')).toBeVisible();

  await page.goto('/');
  await expect(page.getByText('客服处理结果')).toBeVisible();
  await expect(
    page.getByText('承运商已恢复转运，客户接受继续等待。'),
  ).toBeVisible();
  await page.getByRole('button', { name: '查看工单详情' }).click();
  await expect(page.getByText('客服处理方案')).toBeVisible();
  await expect(page.getByText('处理人')).toBeVisible();
  await expect(page.getByText('沈清禾').last()).toBeVisible();
});

test('退款必须明确确认后才执行', async ({ page }) => {
  await page
    .getByRole('button', { name: /申请退款/ })
    .first()
    .click();
  await expect(page.getByText('退款确认')).toBeVisible();
  await expect(
    page.getByText('¥329.00', { exact: true }).first(),
  ).toBeVisible();
  await page.getByRole('button', { name: '确认退款' }).click();
  await expect(page.getByText(/退款已模拟完成/)).toBeVisible();
  await expect(page.getByText('已退款')).toBeVisible();
});

test('运营人员发布知识新版本并替换当前条款', async ({ page }) => {
  await page.goto('/knowledge');
  await expect(page.getByRole('heading', { name: '知识条款与版本' })).toBeVisible();
  await expect(page.getByText('12').first()).toBeVisible();

  await page.getByLabel('版本').fill('2026-09');
  await page.getByLabel('条款号').fill('第 2.1 条');
  await page.getByLabel('关键词').fill('退货 无理由 10天 签收');
  await page
    .getByLabel('条款内容')
    .fill('大多数商品支持签收后 10 天内无理由退货，商品与赠品需保持完整。');
  await page.getByLabel('来源地址').fill('kb://after-sales/2026-09/第-2.1-条');
  await page.getByRole('button', { name: '发布并立即生效' }).click();

  await expect(page.getByText(/第 2.1 条 · 2026-09 已发布/)).toBeVisible();
  await expect(page.getByRole('cell', { name: '2026-09' })).toBeVisible();
  await expect(page.getByText('历史版本').first()).toBeVisible();
});

test('运营看板汇总真实工单、人工接管与工具质量', async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 800 });
  await page
    .getByRole('button', { name: /物流异常建单/ })
    .first()
    .click();
  await expect(page.getByText(/已创建物流异常工单 TK-/)).toBeVisible();
  await page.getByRole('button', { name: '查看工单详情' }).click();
  await page.getByRole('button', { name: '转人工处理' }).click();
  await expect(page.getByText('人工接管已建立')).toBeVisible();

  await page.goto('/operations');
  await expect(page.getByRole('heading', { name: '运营质量总览' })).toBeVisible();
  await expect(page.getByLabel('活动工单').getByText('1', { exact: true })).toBeVisible();
  await expect(page.getByLabel('人工接管').getByText('1', { exact: true })).toBeVisible();
  await expect(page.getByText('100%')).toBeVisible();
  await expect(page.getByRole('cell', { name: '物流专员组' })).toBeVisible();
});
