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

test('物流异常创建幂等工单', async ({ page }) => {
  await page
    .getByRole('button', { name: /物流异常建单/ })
    .first()
    .click();
  await expect(page.getByText(/已调用 create_ticket/)).toBeVisible();
  await expect(page.getByText(/已创建物流异常工单 TK-/)).toBeVisible();
  await expect(page.getByText(/TK-/).last()).toBeVisible();

  await page
    .getByRole('button', { name: /物流异常建单/ })
    .first()
    .click();
  await expect(page.getByText(/已创建物流异常工单 TK-/)).toBeVisible();
  const businessContext = page.getByRole('complementary').last();
  await expect(businessContext.getByText(/TK-/)).toBeVisible();
  await expect(businessContext.getByText('处理中')).toBeVisible();
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
  await expect(page.getByRole('button', { name: '已分派人工' })).toBeDisabled();
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
